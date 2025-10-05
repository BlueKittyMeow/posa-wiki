// Posa Wiki - Main JavaScript
// Dark hacker girl aesthetic with fairyfloss theme

document.addEventListener('DOMContentLoaded', function() {
    // Theme switching
    initThemeSwitcher();

    // Mobile sidebar toggle
    const sidebar = document.querySelector('.sidebar');
    const mainContent = document.querySelector('.main-content');

    // Add mobile menu button if needed
    if (window.innerWidth <= 768) {
        createMobileToggle();
    }

    // Handle window resize
    window.addEventListener('resize', function() {
        if (window.innerWidth <= 768 && !document.querySelector('.mobile-toggle')) {
            createMobileToggle();
        } else if (window.innerWidth > 768) {
            const toggle = document.querySelector('.mobile-toggle');
            if (toggle) toggle.remove();
            sidebar.classList.remove('open');
        }
    });
});

function createMobileToggle() {
    const toggle = document.createElement('button');
    toggle.className = 'mobile-toggle btn';
    toggle.innerHTML = '☰ Menu';
    toggle.style.cssText = 'position: fixed; top: 1rem; left: 1rem; z-index: 200;';
    
    toggle.addEventListener('click', function() {
        document.querySelector('.sidebar').classList.toggle('open');
    });
    
    document.body.appendChild(toggle);
}

// Date picker utilities
function formatDate(date) {
    return date.toISOString().split('T')[0];
}

function goToDate(dateStr) {
    if (dateStr) {
        window.location.href = `/date/${dateStr}`;
    }
}

// Search enhancements
function handleSearchForm(event) {
    const query = event.target.querySelector('input[name="q"]').value.trim();
    if (!query) {
        event.preventDefault();
        alert('Please enter a search term');
    }
}

// Video card interactions
function highlightVideoCard(card) {
    card.style.transform = 'translateY(-8px)';
}

function resetVideoCard(card) {
    card.style.transform = 'translateY(-4px)';
}

// Modal functionality for future use
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = 'auto';
    }
}

// Close modal on backdrop click
document.addEventListener('click', function(event) {
    if (event.target.classList.contains('modal-backdrop')) {
        closeModal(event.target.id);
    }
});

// Keyboard shortcuts
document.addEventListener('keydown', function(event) {
    // Escape key closes modals
    if (event.key === 'Escape') {
        const openModal = document.querySelector('.modal[style*="display: flex"]');
        if (openModal) {
            closeModal(openModal.id);
        }
    }
    
    // Ctrl/Cmd + K for search focus
    if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
        event.preventDefault();
        const searchInput = document.querySelector('input[type="search"]');
        if (searchInput) {
            searchInput.focus();
        }
    }
});

// Theme Switcher
function initThemeSwitcher() {
    const themeButtons = document.querySelectorAll('.theme-btn');
    const currentTheme = localStorage.getItem('posa-wiki-theme') || 'fairyfloss';

    // Apply saved theme on load
    applyTheme(currentTheme);

    // Add click handlers to theme buttons
    themeButtons.forEach(button => {
        button.addEventListener('click', function() {
            const theme = this.dataset.theme;
            applyTheme(theme);
            localStorage.setItem('posa-wiki-theme', theme);
        });
    });
}

function applyTheme(theme) {
    const root = document.documentElement;
    const themeButtons = document.querySelectorAll('.theme-btn');

    // Remove all theme classes
    root.classList.remove('theme-fairyfloss', 'theme-professional');

    // Add the selected theme class (fairyfloss is default, so only add class for professional)
    if (theme === 'professional') {
        root.classList.add('theme-professional');
    }

    // Update active button state
    themeButtons.forEach(btn => {
        if (btn.dataset.theme === theme) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    console.log(`🎨 Theme switched to: ${theme}`);
}

console.log('🌈 Posa Wiki loaded - Fairyfloss Dark theme active!');