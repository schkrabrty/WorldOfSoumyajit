/* Shared keyboard behavior for existing and newly created pages. */
(function() {
    'use strict';
    const menu = document.getElementById('menu');
    const opener = document.querySelector('#header a[href="#menu"]');
    if (menu && opener) {
        let wasOpen = false, background = [];
        const controls = () => [...menu.querySelectorAll('a[href],button,[tabindex="0"]')]
            .filter(item => !item.disabled && getComputedStyle(item).display !== 'none');
        const focusFirst = () => (controls()[0] || menu).focus({preventScroll: true});
        menu.setAttribute('tabindex', '-1');
        const syncMenu = () => {
            const open = document.body.classList.contains('is-menu-visible');
            const previouslyOpen = wasOpen;
            wasOpen = open;
            opener.setAttribute('aria-expanded', String(open));
            menu.setAttribute('aria-hidden', String(!open));
            menu.toggleAttribute('inert', !open);
            if (open && !previouslyOpen) {
                background = [document.getElementById('wrapper'), document.querySelector('.skip-link')]
                    .filter(Boolean).map(element => [element, element.hasAttribute('inert')]);
                background.forEach(([element]) => element.setAttribute('inert', ''));
                // Safari can defer visibility/inert updates until the next frame.
                menu.getBoundingClientRect();
                focusFirst();
                (window.requestAnimationFrame || (callback => window.setTimeout(callback, 0)))(() => {
                    if (wasOpen && !menu.contains(document.activeElement)) focusFirst();
                });
            } else if (!open && previouslyOpen) {
                background.forEach(([element, inert]) => element.toggleAttribute('inert', inert));
                background = [];
                opener.focus({preventScroll: true});
            }
        };
        document.addEventListener('click', event => {
            const trigger = event.target.closest('a[href="#menu"]');
            if (!trigger) return;
            event.preventDefault();
            event.stopPropagation();
            if (menu.contains(trigger)) document.body.classList.remove('is-menu-visible');
            else document.body.classList.toggle('is-menu-visible');
        }, true);
        opener.addEventListener('keydown', event => {
            if (event.key === ' ') {event.preventDefault();opener.click();}
        });
        document.addEventListener('keydown', event => {
            if (!wasOpen) return;
            if (event.key === 'Escape') {
                event.preventDefault();event.stopPropagation();
                document.body.classList.remove('is-menu-visible');
            } else if (event.key === 'Tab') {
                const items = controls(), first = items[0], last = items.at(-1);
                if (!first) {event.preventDefault();menu.focus();}
                else if (event.shiftKey && (document.activeElement === first || !menu.contains(document.activeElement) || document.activeElement === menu)) {
                    event.preventDefault();last.focus();
                } else if (!event.shiftKey && (document.activeElement === last || !menu.contains(document.activeElement) || document.activeElement === menu)) {
                    event.preventDefault();first.focus();
                }
            }
        }, true);
        document.addEventListener('focusin', event => {
            if (wasOpen && !menu.contains(event.target)) focusFirst();
        });
        new MutationObserver(syncMenu).observe(document.body, {attributes: true, attributeFilter: ['class']});
        syncMenu();
    }

    // Mark clearly Bengali passages while preserving explicit author language choices.
    document.querySelectorAll('#main p,#main li,#main figcaption').forEach(element => {
        const language = element.closest('[lang]');
        if (language && language !== document.documentElement) return;
        const text = element.textContent;
        const bengali = (text.match(/[\u0980-\u09ff]/g) || []).length;
        const latin = (text.match(/[a-z]/gi) || []).length;
        if (bengali > 20 && bengali > latin) element.setAttribute('lang', 'bn');
    });
})();
