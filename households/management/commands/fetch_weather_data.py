import urllib.request
import json
from django.core.management.base import BaseCommand
from households.models import WeatherSnapshot
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fetches live weather data from Open-Meteo for Santa Rita municipality and saves it as a WeatherSnapshot'

    def handle(self, *args, **options):
        # Santa Rita coordinates
        latitude = 14.9993
        longitude = 120.6117
        
        url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=wind_speed_10m,precipitation&hourly=wind_speed_10m,precipitation&timezone=auto"
        
        self.stdout.write(self.style.NOTICE(f"Fetching weather data from {url}..."))
        
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'SARA-Capstone-Project/1.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    
                    current_wind_speed = data.get('current', {}).get('wind_speed_10m', 0.0)
                    current_precipitation = data.get('current', {}).get('precipitation', 0.0)
                    
                    # Create a successful snapshot
                    snapshot = WeatherSnapshot.objects.create(
                        current_wind_speed_kmh=current_wind_speed,
                        current_precipitation_mm=current_precipitation,
                        forecast_data=data,
                        fetch_successful=True
                    )
                    
                    self.stdout.write(self.style.SUCCESS(f"Successfully fetched weather data: Wind {current_wind_speed} km/h, Precip {current_precipitation} mm"))
                else:
                    self.stdout.write(self.style.ERROR(f"Failed to fetch data: HTTP {response.status}"))
                    WeatherSnapshot.objects.create(
                        current_wind_speed_kmh=0,
                        current_precipitation_mm=0,
                        forecast_data={},
                        fetch_successful=False
                    )
        except Exception as e:
            logger.error(f"Error fetching weather data: {e}")
            self.stdout.write(self.style.ERROR(f"Exception occurred: {e}"))
            
            # Create a failed snapshot so we log the failure, but previous successful fetches remain valid
            WeatherSnapshot.objects.create(
                current_wind_speed_kmh=0,
                current_precipitation_mm=0,
                forecast_data={'error': str(e)},
                fetch_successful=False
            )
