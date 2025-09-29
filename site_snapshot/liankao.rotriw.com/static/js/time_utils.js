/**
 * Unified time handling utilities for client-side rendering.
 * 
 * This module provides consistent time formatting and timezone conversion
 * for all time displays in the application.
 */

window.TimeUtils = (function() {
    'use strict';
    
    /**
     * Format a datetime to local timezone with consistent format
     * @param {Date|string|number} input - Date object, ISO string, or timestamp
     * @param {string} format - 'datetime', 'date', 'time', or 'relative'
     * @returns {string} Formatted time string
     */
    function formatTime(input, format = 'datetime') {
        let date;
        
        if (input instanceof Date) {
            date = input;
        } else if (typeof input === 'string') {
            // Force UTC interpretation if no timezone info
            if (!input.match(/[Z\+\-]\d{2}:?\d{2}?$/)) {
                input = input + 'Z';
            }
            date = new Date(input);
        } else if (typeof input === 'number') {
            // Timestamp
            date = new Date(input * 1000);
        } else {
            return 'Invalid Date';
        }
        
        if (isNaN(date.getTime())) {
            return 'Invalid Date';
        }
        
        switch (format) {
            case 'date':
                return date.toLocaleDateString();
            case 'time':
                return date.toLocaleTimeString();
            case 'relative':
                return formatRelativeTime(date);
            case 'datetime':
            default:
                return date.toLocaleString();
        }
    }
    
    /**
     * Format relative time (e.g., "2 hours ago")
     * @param {Date} date 
     * @returns {string}
     */
    function formatRelativeTime(date) {
        const now = new Date();
        const diffMs = now - date;
        const diffMinutes = Math.floor(diffMs / (1000 * 60));
        const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
        
        if (diffMinutes < 1) {
            return '刚刚';
        } else if (diffMinutes < 60) {
            return `${diffMinutes}分钟前`;
        } else if (diffHours < 24) {
            return `${diffHours}小时前`;
        } else if (diffDays < 7) {
            return `${diffDays}天前`;
        } else {
            return date.toLocaleDateString();
        }
    }
    
    /**
     * Initialize time displays on the page
     * Converts all elements with .time-display class to local time
     */
    function initTimeDisplays() {
        const elements = document.querySelectorAll('.time-display');
        elements.forEach(element => {
            const timeData = element.dataset.time;
            const timestamp = element.dataset.timestamp;
            const format = element.dataset.format || 'datetime';
            
            if (timeData || timestamp) {
                const input = timestamp ? parseFloat(timestamp) : timeData;
                const formatted = formatTime(input, format);
                element.textContent = formatted;
                
                // Add tooltip with original UTC time
                if (timeData) {
                    const utcDate = new Date(timeData);
                    element.title = `UTC: ${utcDate.toISOString().replace('T', ' ').replace(/\..+/, '')}`;
                }
            }
        });
    }
    
    /**
     * jQuery plugin for easier integration
     */
    if (typeof jQuery !== 'undefined') {
        jQuery.fn.formatTime = function(format = 'datetime') {
            return this.each(function() {
                const $element = jQuery(this);
                const timeData = $element.data('time');
                const timestamp = $element.data('timestamp');
                const elementFormat = $element.data('format') || format;
                
                if (timeData || timestamp) {
                    const input = timestamp ? parseFloat(timestamp) : timeData;
                    const formatted = formatTime(input, elementFormat);
                    $element.text(formatted);
                    
                    // Add tooltip with original UTC time
                    if (timeData) {
                        const utcDate = new Date(timeData);
                        $element.attr('title', `UTC: ${utcDate.toISOString().replace('T', ' ').replace(/\..+/, '')}`);
                    }
                }
            });
        };
    }
    
    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTimeDisplays);
    } else {
        initTimeDisplays();
    }
    
    // Re-initialize when new content is added dynamically
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.addedNodes.length > 0) {
                // Check if any added nodes contain time-display elements
                mutation.addedNodes.forEach(function(node) {
                    if (node.nodeType === 1) { // Element node
                        const timeElements = node.querySelectorAll ? 
                            node.querySelectorAll('.time-display') : [];
                        if (timeElements.length > 0 || node.classList?.contains('time-display')) {
                            setTimeout(initTimeDisplays, 10); // Small delay to ensure DOM is ready
                        }
                    }
                });
            }
        });
    });
    
    function observeBody() {
        if (document.body) {
            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
        } else {
            document.addEventListener('DOMContentLoaded', function() {
                observer.observe(document.body, {
                    childList: true,
                    subtree: true
                });
            });
        }
    }
    observeBody();
    
    // Public API
    return {
        formatTime: formatTime,
        formatRelativeTime: formatRelativeTime,
        initTimeDisplays: initTimeDisplays
    };
})();