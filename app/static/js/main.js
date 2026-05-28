document.addEventListener('DOMContentLoaded', function () {
    // --- THEME SWITCHER LOGIC ---
    const themeSwitcherBtn = document.getElementById('theme-switcher-btn');
    const themeIcon = document.getElementById('theme-icon');

    const getStoredTheme = () => localStorage.getItem('theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    const setStoredTheme = theme => localStorage.setItem('theme', theme);

    const updateIcon = (theme) => {
        themeIcon.className = 'bi';
        if (theme === 'dark') {
            themeIcon.classList.add('bi-sun-fill');
        } else {
            themeIcon.classList.add('bi-moon-stars-fill');
        }
    };

    updateIcon(getStoredTheme());

    if (themeSwitcherBtn) {
        themeSwitcherBtn.addEventListener('click', () => {
            const currentTheme = getStoredTheme();
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            setStoredTheme(newTheme);
            document.documentElement.setAttribute('data-bs-theme', newTheme);
            updateIcon(newTheme);
        });
    }

    // --- PARTICLES.JS CONFIGURATION (MACRO CRM DATA NETWORK STYLE) ---
    if (document.getElementById('particles-js')) {
        particlesJS('particles-js', {
            "particles": {
                "number": {
                    "value": 50,
                    "density": { "enable": true, "value_area": 1000 }
                },
                "color": { "value": "#00B368" },
                "shape": { "type": "circle" },
                "opacity": {
                    "value": 0.4,
                    "random": false
                },
                "size": {
                    "value": 3,
                    "random": true
                },
                "line_linked": {
                    "enable": true,
                    "distance": 150,
                    "color": "#00B368",
                    "opacity": 0.3,
                    "width": 1
                },
                "move": {
                    "enable": true,
                    "speed": 1.5,
                    "direction": "none",
                    "random": false,
                    "straight": false,
                    "out_mode": "out",
                    "bounce": false
                }
            },
            "interactivity": {
                "detect_on": "canvas",
                "events": {
                    "onhover": {
                        "enable": true,
                        "mode": "grab"
                    },
                    "onclick": {
                        "enable": true,
                        "mode": "push"
                    },
                    "resize": true
                },
                "modes": {
                    "grab": {
                        "distance": 180,
                        "line_linked": { "opacity": 0.6 }
                    },
                    "push": { "particles_nb": 3 }
                }
            },
            "retina_detect": true
        });
    }
});