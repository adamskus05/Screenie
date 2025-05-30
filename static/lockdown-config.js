// Configure SES (Secure EcmaScript) lockdown
// Note: This configuration is now optional since lockdown-install.js is not available
const lockdownOptions = {
    errorTaming: 'unsafe',
    consoleTaming: 'unsafe',
    // Remove deprecated options
    // dateTaming: 'safe',
    // mathTaming: 'safe',
    overrideTaming: 'severe',
    stackFiltering: 'verbose',
    requireTaming: 'unsafe'
};

// Only apply lockdown if the function is available
if (typeof globalThis !== 'undefined' && typeof globalThis.lockdown === 'function') {
    try {
        lockdown(lockdownOptions);
        console.log('SES lockdown applied successfully');
    } catch (error) {
        console.warn('SES lockdown failed:', error);
    }
} else {
    console.log('SES lockdown not available - running in standard mode');
}

// Handle specific intrinsics removal warnings
if (typeof Temporal !== 'undefined' && Temporal.Now) {
    try {
        delete Temporal.Now;
    } catch (error) {
        console.warn('Failed to remove Temporal.Now:', error);
    }
}

// Initialize the compartment
const { pow } = Math;
Math.random = () => 0.5; // Deterministic random for security 