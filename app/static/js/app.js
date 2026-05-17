/* ========================================
   WebScraper.pro — Interactive JS
   ======================================== */

document.addEventListener('DOMContentLoaded', () => {
    // --- Mobile Nav Toggle ---
    const toggle = document.getElementById('nav-toggle');
    const links = document.getElementById('nav-links');
    if (toggle && links) {
        toggle.addEventListener('click', () => links.classList.toggle('open'));
    }

    // --- Auto-dismiss Toasts ---
    document.querySelectorAll('.toast[data-auto-dismiss]').forEach(toast => {
        const delay = parseInt(toast.dataset.autoDismiss, 10) || 5000;
        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease forwards';
            setTimeout(() => toast.remove(), 300);
        }, delay);
    });

    // --- Stat Card Entrance Animation ---
    document.querySelectorAll('.stat-card').forEach((card, i) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        setTimeout(() => {
            card.style.transition = 'all 0.5s cubic-bezier(0.4, 0, 0.2, 1)';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, 80 * i);
    });
});

// --- Collapsible Sections ---
function toggleSection(id) {
    const el = document.getElementById(id);
    if (!el) return;
    const header = el.previousElementSibling || el.parentElement.querySelector('.collapsible');
    if (el.style.display === 'none') {
        el.style.display = '';
        if (header) header.classList.remove('collapsed');
    } else {
        el.style.display = 'none';
        if (header) header.classList.add('collapsed');
    }
}

// --- Slide Out animation for toasts ---
const style = document.createElement('style');
style.textContent = `@keyframes slideOut { to { transform: translateX(120%); opacity: 0; } }`;
document.head.appendChild(style);
