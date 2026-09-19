from urllib.parse import urlencode
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.forms import ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse, HttpResponseRedirect
from django.contrib import messages
from django.utils import timezone
from datetime import date, datetime
from django.db.models import Count, Q
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from accounts.decorators import session_protected, mswdo_or_staff_required
from accounts.models import User, Barangay
from households.models import Household, Zone, Family, FamilyMember
from programs.models import Program, AidCategory, Assistance
from distribution.models import AidSchedule, AidClaim, GeneratedBeneficiaryList, GeneratedBeneficiary
from .models import ReportGenerationLog
from .analytics_utils import get_quarterly_report_data, get_beneficiary_list_data
from xhtml2pdf import pisa
from django.template.loader import get_template
from accounts.forms import CreateUserForm
from households.forms import HouseholdForm, FamilyForm, FamilyMemberForm
from programs.forms import ProgramForm, AidCategoryForm, AssistanceForm
# from distribution.forms import AidScheduleForm  # if any

from django.utils.safestring import mark_safe
from distribution.services import get_active_aid_schedule, get_active_schedule
from django.utils.dateparse import parse_datetime
from django_otp.plugins.otp_email.models import EmailDevice
from core.audit_utils import log_action
from django.urls import reverse
from django.core.cache import cache
import json

User = get_user_model()


@login_required
@session_protected
def aid_reports(request):
    if request.user.role not in ('MSWDO', 'MSWDO_STAFF', 'BARANGAY'):
        return HttpResponseForbidden("Access Denied")
    
    # Get all programs with their assistances
    programs = Program.objects.prefetch_related(
        'assistances__aid_category'
    ).filter(is_active=True).order_by('name')

    # For Barangay Admins, only show delegable programs
    if request.user.role == 'BARANGAY':
        programs = programs.filter(allows_barangay_delegation=True)

    # Group assistances by program
    programs_data = []
    for program in programs:
        assistances = program.assistances.filter(is_active=True)
        
        if assistances:
            programs_data.append({
                'program': program,
                'assistances': assistances
            })

    # Calculate summary stats
    total_programs = len(programs_data)
    total_assistance_entries = sum(len(pd['assistances']) for pd in programs_data)
    
    # Scope walk-in claims for Barangay Admins
    if request.user.role == 'BARANGAY':
        total_walkin_claims = AidClaim.objects.filter(
            claim_type='WALK_IN',
            family__household__barangay=request.user.barangay,
            assistance__program__allows_barangay_delegation=True
        ).count()
        total_claims = AidClaim.objects.filter(
            family__household__barangay=request.user.barangay,
            assistance__program__allows_barangay_delegation=True
        ).count()
    else:
        total_walkin_claims = AidClaim.objects.filter(claim_type='WALK_IN').count()
        total_claims = AidClaim.objects.count()

    return render(request, 'reports/aid_reports.html', {
        'programs_data': programs_data,
        'total_programs': total_programs,
        'total_assistance_entries': total_assistance_entries,
        'total_walkin_claims': total_walkin_claims,
        'total_claims': total_claims,
        'now': timezone.now(),
    })


@login_required
@session_protected
@mswdo_or_staff_required
def distribution_claims(request):
    program_id = request.GET.get('program_id')
    assistance_id = request.GET.get('assistance_id')
    selected_barangay = request.GET.get('barangay')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    search_query = request.GET.get('search', '')
    
    program = get_object_or_404(Program, id=program_id, is_active=True)
    assistance = get_object_or_404(Assistance, id=assistance_id, program=program, is_active=True)
    
    # Get all schedules for this assistance
    schedules = AidSchedule.objects.filter(
        assistance=assistance
    ).select_related('barangay').order_by('-schedule_datetime')
    
    # Prioritize schedules based on filters
    # Case 1: Search only (no dates) - prioritize by match count
    # Case 2: Dates only (no search) - prioritize by claim count in date range
    # Case 3: Both search and dates - prioritize by matching claim count in date range
    if (search_query and not date_from and not date_to) or \
       (not search_query and (date_from or date_to)) or \
       (search_query and (date_from or date_to)):
        
        schedules_with_match_count = []
        
        # Parse date filters if present
        date_from_dt = None
        date_to_dt = None
        if date_from:
            try:
                date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
            except ValueError:
                pass
        if date_to:
            try:
                date_to_dt = datetime.strptime(date_to, '%Y-%m-%d')
                from datetime import timedelta
                date_to_dt += timedelta(days=1)
            except ValueError:
                pass
        
        for sched in schedules:
            # Build base queryset for counting (both regular and late scheduled)
            claims_count_qs = AidClaim.objects.filter(
                Q(schedule=sched) | Q(original_schedule=sched)
            )
            
            # Apply date filters if present
            if date_from_dt:
                claims_count_qs = claims_count_qs.filter(claimed_at__gte=date_from_dt)
            if date_to_dt:
                claims_count_qs = claims_count_qs.filter(claimed_at__lt=date_to_dt)
            
            # Apply search filter if present
            if search_query:
                claims_count_qs = claims_count_qs.filter(
                    Q(family__family_name__icontains=search_query) |
                    Q(family_member__first_name__icontains=search_query) |
                    Q(family_member__last_name__icontains=search_query)
                )
            
            match_count = claims_count_qs.count()
            schedules_with_match_count.append((sched, match_count))
        
        # Sort by match count descending, then by schedule_datetime descending
        schedules_with_match_count.sort(key=lambda x: (-x[1], x[0].schedule_datetime), reverse=False)
        schedules = [sched for sched, count in schedules_with_match_count]
    
    # Paginate schedules first (5 per page) before building per-card data
    schedule_page = request.GET.get('schedule_page', 1)
    schedule_paginator = Paginator(schedules, 5)
    schedules_page = schedule_paginator.get_page(schedule_page)
    
    # Generate windowed page range for schedule pagination (e.g., 1 ... 4 5 6 ... 12)
    def get_windowed_page_range(paginator, current_page, window_size=2):
        total_pages = paginator.num_pages
        if total_pages <= 7:  # Show all pages if 7 or fewer
            return range(1, total_pages + 1)
        
        page_range = []
        
        # Always include first page
        page_range.append(1)
        
        # Add ellipsis if needed before window
        if current_page - window_size > 2:
            page_range.append('...')
        
        # Add window around current page
        start = max(2, current_page - window_size)
        end = min(total_pages - 1, current_page + window_size)
        for i in range(start, end + 1):
            page_range.append(i)
        
        # Add ellipsis if needed after window
        if current_page + window_size < total_pages - 1:
            page_range.append('...')
        
        # Always include last page
        if total_pages > 1:
            page_range.append(total_pages)
        
        return page_range
    
    schedule_page_range = get_windowed_page_range(schedule_paginator, schedules_page.number)
    
    # Build schedule data with filtered and paginated claims only for current page
    schedules_data = []
    
    for sched in schedules_page:
        # Get claims for this schedule (both regular and late scheduled)
        claims_queryset = AidClaim.objects.filter(
            Q(schedule=sched) | Q(original_schedule=sched)
        ).select_related(
            'family',
            'family_member',
            'family__household',
            'family__household__barangay',
            'schedule'
        )
        
        # Filter by barangay
        if selected_barangay:
            claims_queryset = claims_queryset.filter(
                family__household__barangay_id=selected_barangay
            )
        
        # Filter by date range
        if date_from:
            try:
                date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
                claims_queryset = claims_queryset.filter(claimed_at__gte=date_from_dt)
            except ValueError:
                pass
        
        if date_to:
            try:
                date_to_dt = datetime.strptime(date_to, '%Y-%m-%d')
                from datetime import timedelta
                date_to_dt += timedelta(days=1)
                claims_queryset = claims_queryset.filter(claimed_at__lt=date_to_dt)
            except ValueError:
                pass
        
        # Search by name (family name or member name)
        if search_query:
            claims_queryset = claims_queryset.filter(
                Q(family__family_name__icontains=search_query) |
                Q(family_member__first_name__icontains=search_query) |
                Q(family_member__last_name__icontains=search_query)
            )
        
        # Order by claimed_at
        claims_queryset = claims_queryset.order_by('-claimed_at')
        
        # Paginate claims for this schedule (5 per page)
        page = request.GET.get(f'page_{sched.id}', 1)
        paginator = Paginator(claims_queryset, 5)
        
        try:
            claims_page = paginator.page(page)
        except PageNotAnInteger:
            claims_page = paginator.page(1)
        except EmptyPage:
            claims_page = paginator.page(paginator.num_pages)
        
        schedules_data.append({
            'schedule': sched,
            'claims': claims_page,
            'paginator': paginator,
            'page_id': f'page_{sched.id}',
            'total_beneficiaries': (
                sched.beneficiary_list.entries.filter(family_member__isnull=False).count() 
                if sched.assistance.beneficiary_type == 'individual' 
                else sched.beneficiary_list.entries.filter(family__isnull=False).count()
            ) if hasattr(sched, 'beneficiary_list') else 0,
        })
    
    barangays = Barangay.objects.all()
    
    return render(request, 'reports/distribution_claims.html', {
        'program': program,
        'assistance': assistance,
        'schedules_data': schedules_data,
        'schedules_page': schedules_page,
        'schedule_paginator': schedule_paginator,
        'schedule_page_range': schedule_page_range,
        'barangays': barangays,
        'selected_barangay': selected_barangay,
        'date_from': date_from,
        'date_to': date_to,
        'search_query': search_query,
        'now': timezone.now(),
    })


@login_required
@session_protected
def barangay_reports(request):
    if request.user.role not in ('MSWDO', 'MSWDO_STAFF', 'BARANGAY'):
        return HttpResponseForbidden("Access Denied")
    
    selected_barangay = request.GET.get('barangay')
    selected_zone = request.GET.get('zone')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    search_query = request.GET.get('search', '')
    
    # Base queryset for walk-in claims only
    claims_queryset = AidClaim.objects.filter(
        claim_type='WALK_IN'
    ).select_related(
        'family',
        'family_member',
        'family__household',
        'family__household__barangay',
        'family__household__zone',
        'assistance',
        'assistance__program',
        'assistance__aid_category'
    )
    
    # Role-based scoping
    assigned_schedules = None
    if request.user.role == 'BARANGAY':
        from distribution.services import is_barangay_delegable, is_staff_assigned_to_scan
        # Barangay Admin: only see claims for their barangay and delegable programs
        claims_queryset = claims_queryset.filter(
            family__household__barangay=request.user.barangay,
            assistance__program__allows_barangay_delegation=True
        )
        selected_barangay = request.user.barangay.id  # Lock filter to their barangay
        
        # Get assigned schedules for Distribution Report Export panel
        assigned_schedules = AidSchedule.objects.filter(
            assignments__staff=request.user,
            assistance__program__allows_barangay_delegation=True
        ).select_related(
            'assistance__program', 'assistance__aid_category'
        ).prefetch_related('assignments').order_by('-schedule_datetime')
    elif request.user.role == 'MSWDO_STAFF':
        # MSWDO Staff: no automatic scoping (can filter manually)
        pass
    # MSWDO: no scoping (can see all)
    
    # For Barangay Admins, don't pass claims to template (they don't see walk-in claims table)
    if request.user.role == 'BARANGAY':
        claims_page = None
        paginator = None
    
    # Filter by barangay (for MSWDO/MSWDO_STAFF manual filtering)
    if selected_barangay and request.user.role != 'BARANGAY':
        claims_queryset = claims_queryset.filter(
            family__household__barangay_id=selected_barangay
        )
    
    # Filter by zone
    if selected_zone:
        claims_queryset = claims_queryset.filter(
            family__household__zone_id=selected_zone
        )
    
    # Filter by date range
    if date_from:
        try:
            date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
            claims_queryset = claims_queryset.filter(claimed_at__gte=date_from_dt)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_dt = datetime.strptime(date_to, '%Y-%m-%d')
            from datetime import timedelta
            date_to_dt += timedelta(days=1)
            claims_queryset = claims_queryset.filter(claimed_at__lt=date_to_dt)
        except ValueError:
            pass
    
    # Search by name (family name or member name)
    if search_query:
        claims_queryset = claims_queryset.filter(
            Q(family__family_name__icontains=search_query) |
            Q(family_member__first_name__icontains=search_query) |
            Q(family_member__last_name__icontains=search_query)
        )
    
    # Deterministic ordering to avoid pagination bug
    claims_queryset = claims_queryset.order_by('-claimed_at', 'id')
    
    # Paginate claims (20 per page)
    page = request.GET.get('page', 1)
    paginator = Paginator(claims_queryset, 20)
    
    try:
        claims_page = paginator.page(page)
    except PageNotAnInteger:
        claims_page = paginator.page(1)
    except EmptyPage:
        claims_page = paginator.page(paginator.num_pages)
    
    barangays = Barangay.objects.all()
    
    # For Barangay Admins, scope zones to their barangay only
    if request.user.role == 'BARANGAY':
        all_zones = Zone.objects.filter(barangay=request.user.barangay)
    else:
        all_zones = Zone.objects.all()
    
    return render(request, 'reports/barangay_reports.html', {
        'claims': claims_page,
        'paginator': paginator,
        'barangays': barangays,
        'all_zones': all_zones,
        'selected_barangay': selected_barangay,
        'selected_zone': selected_zone,
        'date_from': date_from,
        'date_to': date_to,
        'search_query': search_query,
        'now': timezone.now(),
        'is_barangay': request.user.role == 'BARANGAY',
        'assigned_schedules': assigned_schedules,
    })


@login_required
@session_protected
def generate_summary_report(request):
    if request.user.role == 'BARANGAY':
        from distribution.services import is_barangay_delegable, is_staff_assigned_to_scan
        barangay_id = request.GET.get('barangay')
        if barangay_id:
            barangay = get_object_or_404(Barangay, id=barangay_id)
            if barangay != request.user.barangay:
                return HttpResponseForbidden("You can only generate reports for your own barangay.")
        else:
            barangay = request.user.barangay
    elif request.user.role in ('MSWDO', 'MSWDO_STAFF'):
        barangay_id = request.GET.get('barangay')
        barangay = get_object_or_404(Barangay, id=barangay_id) if barangay_id else None
    else:
        return HttpResponseForbidden("Access Denied")
        
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    if not start_date_str or not end_date_str:
        return HttpResponse("Missing date range.", status=400)
        
    from django.utils.dateparse import parse_datetime
    start_date = parse_datetime(start_date_str + "T00:00:00").date()
    end_date = parse_datetime(end_date_str + "T23:59:59").date()
    
    data = get_quarterly_report_data(start_date, end_date, barangay=barangay)
    
    chart_image = None
    if len(data['months']) > 1:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import io, base64
        
        fig, ax = plt.subplots(figsize=(8, 4))
        
        months = [m['month_label'] for m in data['months']]
        categories = set()
        for m in data['months']:
            for c in m['categories']:
                categories.add(c['name'])
        categories = list(categories)
        categories.sort()
        
        x = range(len(months))
        width = 0.8 / max(1, len(categories))
        
        for i, cat in enumerate(categories):
            counts = []
            for m in data['months']:
                count = next((c['count'] for c in m['categories'] if c['name'] == cat), 0)
                counts.append(count)
            ax.bar([pos + i*width for pos in x], counts, width, label=cat)
            
        ax.set_xticks([pos + width*(len(categories)-1)/2 for pos in x])
        ax.set_xticklabels(months)
        ax.legend()
        
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        plt.close(fig)
        chart_image = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode('utf-8')
        
    context = {
        'data': data,
        'generated_at': timezone.now(),
        'chart_image': chart_image
    }
    
    template = get_template('reports/summary_report_pdf.html')
    html = template.render(context)
    
    from django.http import HttpResponse
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Summary_Report.pdf"'
    
    pisa_status = pisa.CreatePDF(html, dest=response)
    
    if not pisa_status.err:
        report_log = ReportGenerationLog.objects.create(
            report_type='SUMMARY',
            period_label=data['period_label'],
            generated_by=request.user
        )
        log_action(request.user, 'REPORT_GENERATED', target=report_log, description=f"Generated SUMMARY report for {data['period_label']}")
        return response
    return HttpResponse("Error generating PDF", status=500)


@login_required
@session_protected
def generate_beneficiary_list_report(request):
    if request.user.role != 'MSWDO_STAFF':
        return HttpResponseForbidden("Only MSWDO Staff can generate this report.")
        
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    if not start_date_str or not end_date_str:
        return HttpResponse("Missing date range.", status=400)
        
    from django.utils.dateparse import parse_datetime
    start_date = parse_datetime(start_date_str + "T00:00:00").date()
    end_date = parse_datetime(end_date_str + "T23:59:59").date()
    
    data = get_beneficiary_list_data(start_date, end_date)
    
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Beneficiary List"
    
    headers = ["Name", "Barangay", "Zone", "Assistance/Category", "Date Claimed"]
    
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.fill = PatternFill(start_color='D3D3D3', end_color='D3D3D3', fill_type='solid')
        
    column_widths = [30, 25, 20, 35, 20]
    for col_idx, width in enumerate(column_widths, start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = width
        
    for row_idx, row_data in enumerate(data, start=2):
        ws.cell(row=row_idx, column=1, value=row_data['name'])
        ws.cell(row=row_idx, column=2, value=row_data['barangay'])
        ws.cell(row=row_idx, column=3, value=row_data['zone'])
        ws.cell(row=row_idx, column=4, value=row_data['assistance'])
        claimed_date_str = timezone.localtime(row_data['claimed_at']).strftime('%Y-%m-%d %H:%M')
        ws.cell(row=row_idx, column=5, value=claimed_date_str)
        
    from django.http import HttpResponse
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="Beneficiary_List_Report.xlsx"'
    
    wb.save(response)
    wb.close()
    
    from django.utils.dateformat import DateFormat
    period_label = f"{DateFormat(start_date).format('F Y')} to {DateFormat(end_date).format('F Y')}"
    report_log = ReportGenerationLog.objects.create(
        report_type='BENEFICIARY_LIST',
        period_label=period_label,
        generated_by=request.user
    )
    log_action(request.user, 'REPORT_GENERATED', target=report_log, description=f"Generated BENEFICIARY_LIST report for {period_label}")
    
    return response


@login_required
@session_protected
def generate_walkin_summary_report(request):
    if request.user.role != 'MSWDO_STAFF':
        return HttpResponseForbidden("Only MSWDO Staff can generate this report.")
        
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    if not start_date_str or not end_date_str:
        return HttpResponse("Missing date range.", status=400)
        
    from django.utils.dateparse import parse_datetime
    start_date = parse_datetime(start_date_str + "T00:00:00").date()
    end_date = parse_datetime(end_date_str + "T23:59:59").date()
    
    data = get_quarterly_report_data(start_date, end_date, claim_type='WALK_IN')
    
    chart_image = None
    if len(data['months']) > 1:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import io, base64
        
        fig, ax = plt.subplots(figsize=(8, 4))
        
        months = [m['month_label'] for m in data['months']]
        categories = set()
        for m in data['months']:
            for c in m['categories']:
                categories.add(c['name'])
        categories = list(categories)
        categories.sort()
        
        x = range(len(months))
        width = 0.8 / max(1, len(categories))
        
        for i, cat in enumerate(categories):
            counts = []
            for m in data['months']:
                count = next((c['count'] for c in m['categories'] if c['name'] == cat), 0)
                counts.append(count)
            ax.bar([pos + i*width for pos in x], counts, width, label=cat)
            
        ax.set_xticks([pos + width*(len(categories)-1)/2 for pos in x])
        ax.set_xticklabels(months)
        ax.legend()
        
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        plt.close(fig)
        chart_image = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode('utf-8')
        
    context = {
        'data': data,
        'generated_at': timezone.now(),
        'chart_image': chart_image
    }
    
    template = get_template('reports/summary_report_pdf.html')
    html = template.render(context)
    
    from django.http import HttpResponse
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Walkin_Summary_Report.pdf"'
    
    pisa_status = pisa.CreatePDF(html, dest=response)
    
    if not pisa_status.err:
        report_log = ReportGenerationLog.objects.create(
            report_type='WALKIN_SUMMARY',
            period_label=data['period_label'],
            generated_by=request.user
        )
        log_action(request.user, 'REPORT_GENERATED', target=report_log, description=f"Generated WALKIN_SUMMARY report for {data['period_label']}")
        return response
    return HttpResponse("Error generating PDF", status=500)


@login_required
@session_protected
def generate_walkin_beneficiary_list_report(request):
    if request.user.role != 'MSWDO_STAFF':
        return HttpResponseForbidden("Only MSWDO Staff can generate this report.")
        
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    if not start_date_str or not end_date_str:
        return HttpResponse("Missing date range.", status=400)
        
    from django.utils.dateparse import parse_datetime
    start_date = parse_datetime(start_date_str + "T00:00:00").date()
    end_date = parse_datetime(end_date_str + "T23:59:59").date()
    
    data = get_beneficiary_list_data(start_date, end_date, claim_type='WALK_IN')
    
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Walk-in Beneficiary List"
    
    headers = ["Name", "Barangay", "Zone", "Assistance/Category", "Date Claimed"]
    
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.fill = PatternFill(start_color='D3D3D3', end_color='D3D3D3', fill_type='solid')
        
    column_widths = [30, 25, 20, 35, 20]
    for col_idx, width in enumerate(column_widths, start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = width
        
    for row_idx, row_data in enumerate(data, start=2):
        ws.cell(row=row_idx, column=1, value=row_data['name'])
        ws.cell(row=row_idx, column=2, value=row_data['barangay'])
        ws.cell(row=row_idx, column=3, value=row_data['zone'])
        ws.cell(row=row_idx, column=4, value=row_data['assistance'])
        claimed_date_str = timezone.localtime(row_data['claimed_at']).strftime('%Y-%m-%d %H:%M')
        ws.cell(row=row_idx, column=5, value=claimed_date_str)
        
    from django.http import HttpResponse
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="Walkin_Beneficiary_List_Report.xlsx"'
    
    wb.save(response)
    wb.close()
    
    from django.utils.dateformat import DateFormat
    period_label = f"{DateFormat(start_date).format('F Y')} to {DateFormat(end_date).format('F Y')}"
    report_log = ReportGenerationLog.objects.create(
        report_type='WALKIN_BENEFICIARY_LIST',
        period_label=period_label,
        generated_by=request.user
    )
    log_action(request.user, 'REPORT_GENERATED', target=report_log, description=f"Generated WALKIN_BENEFICIARY_LIST report for {period_label}")
    
    return response


@login_required
@session_protected
def distribution_report(request, schedule_id):
    """
    Display distribution report for a specific schedule.
    Shows claimed and unclaimed beneficiaries.
    For Barangay Admins, only allows access to their barangay's delegable schedules.
    """
    schedule = get_object_or_404(
        AidSchedule.objects.select_related(
            'assistance', 'assistance__program', 'assistance__aid_category'
        ),
        id=schedule_id
    )
    
    # Role-based access control
    if request.user.role == 'BARANGAY':
        from distribution.services import is_barangay_delegable, is_staff_assigned_to_scan
        # Barangay Admins can only view reports for their barangay's delegable schedules they are assigned to
        if not is_barangay_delegable(schedule):
            return HttpResponseForbidden("This schedule is not delegable for Barangay Admins.")
        if schedule.barangay != request.user.barangay:
            return HttpResponseForbidden("This schedule is not in your barangay.")
        if not is_staff_assigned_to_scan(request.user, schedule):
            return HttpResponseForbidden("You are not assigned to this schedule.")
    elif request.user.role not in ('MSWDO', 'MSWDO_STAFF'):
        return HttpResponseForbidden("Access Denied")
    
    # Get beneficiary list if exists
    total_beneficiaries = 0
    unclaimed_beneficiaries = []
    
    if hasattr(schedule, 'beneficiary_list'):
        ben_list = schedule.beneficiary_list
        total_beneficiaries = ben_list.entries.count()
        
        # Get claimed beneficiaries (including OFFLINE_IMPORT and late scheduled WALK_IN claims)
        claimed_family_ids = AidClaim.objects.filter(
            Q(schedule=schedule, claim_type__in=['DISTRIBUTION', 'OFFLINE_IMPORT']) |
            Q(original_schedule=schedule, claim_type='WALK_IN', is_late_scheduled_claim=True)
        ).values_list('family_id', flat=True)
        
        # Get unclaimed beneficiaries - handle both family-based and individual-based
        if schedule.assistance.beneficiary_type == 'family':
            # Family-based assistance: filter by family_id
            unclaimed_beneficiaries = ben_list.entries.filter(
                Q(family_id__isnull=False) & ~Q(family_id__in=claimed_family_ids)
            ).select_related(
                'family', 'family__household'
            ).all()
        else:
            # Individual-based assistance: filter by family_member
            claimed_member_ids = AidClaim.objects.filter(
                Q(schedule=schedule, claim_type__in=['DISTRIBUTION', 'OFFLINE_IMPORT']) |
                Q(original_schedule=schedule, claim_type='WALK_IN', is_late_scheduled_claim=True)
            ).values_list('family_member_id', flat=True)
            unclaimed_beneficiaries = ben_list.entries.filter(
                Q(family_member_id__isnull=False) & ~Q(family_member_id__in=claimed_member_ids)
            ).select_related(
                'family_member', 'family_member__family', 'family_member__family__household'
            ).prefetch_related(
                'family_member__family'
            ).all()
    else:
        # No beneficiary list, count from claims only
        total_beneficiaries = schedule.claims.filter(claim_type__in=['DISTRIBUTION', 'OFFLINE_IMPORT']).count()
    
    # Get claimed beneficiaries with details (including OFFLINE_IMPORT and late scheduled WALK_IN claims)
    claimed_beneficiaries = AidClaim.objects.filter(
        Q(schedule=schedule, claim_type__in=['DISTRIBUTION', 'OFFLINE_IMPORT']) |
        Q(original_schedule=schedule, claim_type='WALK_IN', is_late_scheduled_claim=True)
    ).select_related(
        'family', 'family_member', 'created_by'
    ).order_by('claimed_at')
    
    claimed_count = claimed_beneficiaries.count()
    unclaimed_count = total_beneficiaries - claimed_count
    
    # Build back URL for distribution_claims flow
    back_url = None
    if request.GET.get('from') == 'distribution_claims' and request.user.role in ('MSWDO', 'MSWDO_STAFF'):
        params = {}
        if request.GET.get('program_id'):
            params['program_id'] = request.GET.get('program_id')
        if request.GET.get('assistance_id'):
            params['assistance_id'] = request.GET.get('assistance_id')
        if request.GET.get('schedule_page'):
            params['schedule_page'] = request.GET.get('schedule_page')
        if request.GET.get('barangay'):
            params['barangay'] = request.GET.get('barangay')
        if request.GET.get('date_from'):
            params['date_from'] = request.GET.get('date_from')
        if request.GET.get('date_to'):
            params['date_to'] = request.GET.get('date_to')
        if request.GET.get('search'):
            params['search'] = request.GET.get('search')
        back_url = f"{reverse('distribution_claims')}?{urlencode(params)}"
    
    return render(request, 'reports/distribution_report.html', {
        'schedule': schedule,
        'total_beneficiaries': total_beneficiaries,
        'claimed_beneficiaries': claimed_beneficiaries,
        'unclaimed_beneficiaries': unclaimed_beneficiaries,
        'claimed_count': claimed_count,
        'unclaimed_count': unclaimed_count,
        'back_url': back_url,
    })


@login_required
@session_protected
def export_distribution_report(request, schedule_id):
    """
    Export distribution claims data to .xlsx file.
    For Barangay Admins, only allows export for their barangay's delegable schedules they are assigned to.
    """
    from distribution.offline_sync import export_distribution_claims
    from distribution.services import is_barangay_delegable, is_staff_assigned_to_scan
    
    schedule = get_object_or_404(AidSchedule, id=schedule_id)
    
    # Role-based access control
    if request.user.role == 'BARANGAY':
        # Barangay Admins can only export reports for their barangay's delegable schedules they are assigned to
        if not is_barangay_delegable(schedule):
            return HttpResponseForbidden("This schedule is not delegable for Barangay Admins.")
        if schedule.barangay != request.user.barangay:
            return HttpResponseForbidden("This schedule is not in your barangay.")
        if not is_staff_assigned_to_scan(request.user, schedule):
            return HttpResponseForbidden("You are not assigned to this schedule.")
    elif request.user.role not in ('MSWDO', 'MSWDO_STAFF'):
        return HttpResponseForbidden("Access Denied")
    
    filename, xlsx_bytes = export_distribution_claims(schedule)
    
    from django.http import HttpResponse
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write(xlsx_bytes.getvalue())
    
    log_action(request.user, 'EXPORT_DISTRIBUTION_CLAIMS', target=schedule, description=f"Exported distribution claims for schedule {schedule.id}")
    
    return response


@login_required
@session_protected
@mswdo_or_staff_required
def import_distribution_claims_view(request):
    """
    Import distribution claims data from .xlsx file (offline reconciliation).
    """
    from distribution.offline_sync import import_distribution_claims
    
    if request.method == 'POST':
        xlsx_file = request.FILES.get('xlsx_file')
        if not xlsx_file:
            messages.error(request, "Please select a file to upload.")
            return redirect('staff_assigned_schedules')
        
        try:
            schedule = import_distribution_claims(xlsx_file, request.user)
            messages.success(request, f"Successfully imported distribution claims for schedule {schedule.id}. The schedule has been marked as finished (Offline Mode).")
            return redirect('distribution_report', schedule_id=schedule.id)
        except Exception as e:
            messages.error(request, f"Error importing file: {str(e)}")
            return redirect('staff_assigned_schedules')
    
    return HttpResponseForbidden("Invalid Method")
