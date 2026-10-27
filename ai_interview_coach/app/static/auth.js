document.querySelectorAll("[data-toggle-password]").forEach((button) => {
  button.addEventListener("click", () => {
    const input = document.getElementById(button.dataset.togglePassword);
    const showPassword = input.type === "password";
    input.type = showPassword ? "text" : "password";
    button.textContent = showPassword ? "Hide" : "Show";
    button.setAttribute("aria-label", `${showPassword ? "Hide" : "Show"} password`);
  });
});

const registrationForm = document.querySelector('form[action*="register"]');
if (registrationForm) {
  const passwordInput = registrationForm.elements.password;
  const confirmationInput = registrationForm.elements.confirm_password;
  function validatePasswordMatch() {
    confirmationInput.setCustomValidity(
      passwordInput.value === confirmationInput.value ? "" : "Passwords do not match.",
    );
  }
  passwordInput.addEventListener("input", validatePasswordMatch);
  confirmationInput.addEventListener("input", validatePasswordMatch);
  registrationForm.addEventListener("submit", (event) => {
    validatePasswordMatch();
    if (passwordInput.value !== confirmationInput.value) {
      event.preventDefault();
      confirmationInput.reportValidity();
    }
  });
}
