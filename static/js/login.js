// Password Toggle
const togglePassword = document.querySelector('#togglePassword');
const password = document.querySelector('#password');
const icon = togglePassword.querySelector('i');

togglePassword.addEventListener('click', function () {

    const type =
        password.getAttribute('type') === 'password'
        ? 'text'
        : 'password';

    password.setAttribute('type', type);

    icon.classList.toggle('bi-eye-fill');
    icon.classList.toggle('bi-eye-slash-fill');

});

// Loading Button
document.querySelector("#loginForm").addEventListener("submit", function () {

    document.querySelector(".btn-text").innerHTML = `
        <span class="spinner-border spinner-border-sm"></span>
        Signing in...
    `;

});