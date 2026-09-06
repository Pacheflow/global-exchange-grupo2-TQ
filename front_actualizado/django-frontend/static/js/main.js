// Theme Toggle
const themeToggleBtn = document.getElementById('theme-toggle');
const themeIconMoon = document.getElementById('theme-icon-moon');
const themeIconSun = document.getElementById('theme-icon-sun');

function setTheme(isDark) {
    if (isDark) {
        document.documentElement.classList.add('dark');
        localStorage.setItem('theme', 'dark');
        if(themeIconMoon) themeIconMoon.style.display = 'none';
        if(themeIconSun) themeIconSun.style.display = 'block';
    } else {
        document.documentElement.classList.remove('dark');
        localStorage.setItem('theme', 'light');
        if(themeIconMoon) themeIconMoon.style.display = 'block';
        if(themeIconSun) themeIconSun.style.display = 'none';
    }
}

if (themeToggleBtn) {
    themeToggleBtn.addEventListener('click', () => {
        const isDark = document.documentElement.classList.contains('dark');
        setTheme(!isDark);
    });
}

// Initial Theme
const savedTheme = localStorage.getItem('theme');
const prefersDark = window.matchMatchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
    setTheme(true);
} else {
    setTheme(false);
}

// Navbar Scroll Effect
const navbar = document.getElementById('navbar');
window.addEventListener('scroll', () => {
    if (!navbar) return;
    if (window.scrollY > 50) {
        navbar.style.background = document.documentElement.classList.contains('dark') ? 'rgba(6, 11, 30, 0.92)' : 'rgba(240, 245, 255, 0.92)';
        navbar.style.borderBottomColor = 'var(--border)';
        navbar.style.backdropFilter = 'blur(16px)';
    } else {
        navbar.style.background = 'transparent';
        navbar.style.borderBottomColor = 'transparent';
        navbar.style.backdropFilter = 'none';
    }
}, { passive: true });

// User Dropdown
const userDropdownBtn = document.getElementById('user-dropdown-btn');
const userDropdownMenu = document.getElementById('user-dropdown-menu');

if (userDropdownBtn && userDropdownMenu) {
    userDropdownBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const isVisible = userDropdownMenu.style.display === 'block';
        userDropdownMenu.style.display = isVisible ? 'none' : 'block';
    });
    
    document.addEventListener('click', (e) => {
        if (!userDropdownBtn.contains(e.target) && !userDropdownMenu.contains(e.target)) {
            userDropdownMenu.style.display = 'none';
        }
    });
}

// Reveal Animations
document.addEventListener('DOMContentLoaded', () => {
    const reveals = document.querySelectorAll('.reveal');
    const observer = new IntersectionObserver((entries, obs) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                obs.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1 });
    
    reveals.forEach(el => observer.observe(el));
});

// Conversor Logic (Only runs if elements exist)
const amountInput = document.getElementById('conv-amount');
const fromSelect = document.getElementById('conv-from');
const toSelect = document.getElementById('conv-to');
const resultDiv = document.getElementById('conv-result');
const swapBtn = document.getElementById('conv-swap');
const rateDisplay = document.getElementById('conv-rate');

const exchangeRates = {
  USD: { PYG: 7480, EUR: 0.92, BRL: 4.95, ARS: 980, USD: 1 },
  EUR: { PYG: 8120, USD: 1.09, BRL: 5.38, ARS: 1065, EUR: 1 },
  BRL: { PYG: 1510, USD: 0.20, EUR: 0.19, ARS: 198, BRL: 1 },
  ARS: { PYG: 7.6, USD: 0.001, EUR: 0.0009, BRL: 0.005, ARS: 1 },
  PYG: { USD: 0.00013, EUR: 0.00012, BRL: 0.00066, ARS: 0.13, PYG: 1 }
};

function updateConversor() {
    if (!amountInput) return;
    const amount = parseFloat(amountInput.value.replace(/[^0-9.]/g, '')) || 0;
    const from = fromSelect.value;
    const to = toSelect.value;
    
    const rate = exchangeRates[from]?.[to] || 1;
    const result = amount * rate;
    
    resultDiv.textContent = result.toLocaleString('es-PY', { maximumFractionDigits: result < 100 ? 4 : 0 });
    
    // Update rate display
    const displayRateText = rate < 1 
        ? `1 ${to} = ${(1 / rate).toLocaleString('es-PY', { maximumFractionDigits: 2 })} ${from}`
        : `1 ${from} = ${rate.toLocaleString('es-PY', { maximumFractionDigits: 2 })} ${to}`;
    
    if (rateDisplay) {
        rateDisplay.textContent = displayRateText;
    }
}

if (amountInput) {
    amountInput.addEventListener('input', (e) => {
        // Only allow numbers and decimal
        e.target.value = e.target.value.replace(/[^0-9.]/g, '');
        updateConversor();
    });
    fromSelect.addEventListener('change', updateConversor);
    toSelect.addEventListener('change', updateConversor);
    
    swapBtn.addEventListener('click', () => {
        // Animate button
        swapBtn.style.transform = 'rotate(180deg)';
        setTimeout(() => swapBtn.style.transform = 'rotate(0deg)', 320);
        
        const temp = fromSelect.value;
        fromSelect.value = toSelect.value;
        toSelect.value = temp;
        updateConversor();
    });
    
    updateConversor();
}

// Simple animations for price/change (for tables)
document.addEventListener('DOMContentLoaded', () => {
    const animateElements = document.querySelectorAll('.animate-price');
    // Implement simple easing for numbers if needed, mostly static for template
});
