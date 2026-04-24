document.addEventListener('DOMContentLoaded', () => {
    const interactiveSelector = [
        'button',
        '.btn',
        '.action-btn',
        '.filter-btn',
        '.pagination-btn',
        '.nav-link',
        '.sidebar-link',
        '.btn-print',
        '.btn-logout',
        '.question-card',
        '.stat-card',
        '.panel',
        '.card',
        '.summary-item',
        '.question',
        '.header-section',
        '.hero',
        '.upload-section'
    ].join(', ');

    const animatedSelector = [
        '.hero',
        '.panel',
        '.card',
        '.summary-item',
        '.stat-card',
        '.question-card',
        '.question',
        '.header-section',
        '.stats-grid > *',
        '.summary-grid > *',
        '.questions-grid > *'
    ].join(', ');

    document.querySelectorAll(interactiveSelector).forEach((node) => {
        node.classList.add('ui-pressable');
        node.addEventListener('pointerdown', () => node.classList.add('is-pressed'));
        node.addEventListener('pointerup', () => node.classList.remove('is-pressed'));
        node.addEventListener('pointerleave', () => node.classList.remove('is-pressed'));
        node.addEventListener('blur', () => node.classList.remove('is-pressed'));
    });

    document.querySelectorAll(animatedSelector).forEach((node) => {
        node.classList.add('ui-fade-up');
    });

    requestAnimationFrame(() => {
        document.body.classList.add('ui-ready');
    });
});
