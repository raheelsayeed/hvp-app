// Mobile Menu Toggle Functionality
document.addEventListener('DOMContentLoaded', function() {
    const menuToggle = document.querySelector('.menu-toggle');
    const navButtons = document.querySelector('.nav-buttons');
    const body = document.body;
    
    // Create menu toggle button if it doesn't exist
    if (!menuToggle) {
        createMobileMenuToggle();
    }
    
    function createMobileMenuToggle() {
        const headerContent = document.querySelector('.header-content');
        if (!headerContent) return;
        
        const toggleButton = document.createElement('button');
        toggleButton.className = 'menu-toggle';
        toggleButton.setAttribute('aria-label', 'Toggle navigation menu');
        toggleButton.setAttribute('aria-expanded', 'false');
        
        toggleButton.innerHTML = `
            <div class="hamburger">
                <span></span>
                <span></span>
                <span></span>
            </div>
        `;
        
        headerContent.appendChild(toggleButton);
        
        // Add event listener to the newly created button
        toggleButton.addEventListener('click', toggleMobileMenu);
    }
    
    function toggleMobileMenu() {
        const menuToggle = document.querySelector('.menu-toggle');
        const navButtons = document.querySelector('.nav-buttons');
        
        if (!menuToggle || !navButtons) return;
        
        const isOpen = menuToggle.classList.contains('active');
        
        if (isOpen) {
            closeMobileMenu();
        } else {
            openMobileMenu();
        }
    }
    
    function openMobileMenu() {
        const menuToggle = document.querySelector('.menu-toggle');
        const navButtons = document.querySelector('.nav-buttons');
        
        menuToggle.classList.add('active');
        navButtons.classList.add('active');
        menuToggle.setAttribute('aria-expanded', 'true');
        
        // Prevent body scroll when menu is open
        body.style.overflow = 'hidden';
        
        // Add click outside to close
        setTimeout(() => {
            document.addEventListener('click', handleClickOutside);
        }, 100);
    }
    
    function closeMobileMenu() {
        const menuToggle = document.querySelector('.menu-toggle');
        const navButtons = document.querySelector('.nav-buttons');
        
        menuToggle.classList.remove('active');
        navButtons.classList.remove('active');
        menuToggle.setAttribute('aria-expanded', 'false');
        
        // Restore body scroll
        body.style.overflow = '';
        
        // Remove click outside listener
        document.removeEventListener('click', handleClickOutside);
    }
    
    function handleClickOutside(event) {
        const header = document.querySelector('header');
        const menuToggle = document.querySelector('.menu-toggle');
        
        if (!header.contains(event.target)) {
            closeMobileMenu();
        }
    }
    
    // Close menu when clicking on nav links
    const navLinks = document.querySelectorAll('.nav-buttons a, .user-logout');
    navLinks.forEach(link => {
        link.addEventListener('click', () => {
            if (window.innerWidth <= 768) {
                closeMobileMenu();
            }
        });
    });
    
    // Handle window resize
    window.addEventListener('resize', function() {
        if (window.innerWidth > 768) {
            closeMobileMenu();
        }
    });
    
    // Handle escape key
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape') {
            const menuToggle = document.querySelector('.menu-toggle');
            if (menuToggle && menuToggle.classList.contains('active')) {
                closeMobileMenu();
            }
        }
    });
    
    // Add initial event listener if toggle button already exists
    const existingToggle = document.querySelector('.menu-toggle');
    if (existingToggle) {
        existingToggle.addEventListener('click', toggleMobileMenu);
    }
});