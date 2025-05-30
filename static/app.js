// @ts-check
// Content-Type: application/javascript; charset=utf-8

// Define types at the top
/**
 * @typedef {Object} Screenshot
 * @property {string} name
 * @property {string} path
 * @property {string} created
 * @property {string} modified
 * @property {number} size
 */

/**
 * @typedef {Object} Folder
 * @property {string} name
 * @property {string} display_name
 * @property {string} path
 * @property {string} created
 * @property {string} modified
 * @property {boolean} is_permanent
 * @property {boolean} is_starred
 * @property {Screenshot[]} screenshots
 */

/**
 * @typedef {Object} FoldersResponse
 * @property {Folder[]} folders
 * @property {string} default_folder
 */

// Global state
/** @type {Folder | null} */
let currentFolder = null;
/** @type {{ path: string, name: string, date: string } | null} */
let currentScreenshot = null;
/** @type {Set<string>} */
let selectedScreenshots = new Set();
/** @type {boolean} */
let isMultiSelectMode = false;

// Add at the top with other global variables
/** @type {Map<string, string>} */
const imageCache = new Map();
/** @type {Map<string, Promise<string>>} */
const loadingImages = new Map();
const folderTemplate = document.createElement('template');
const screenshotTemplate = document.createElement('template');
/** @type {{ data: FoldersResponse | null, timestamp: number, maxAge: number }} */
const folderCache = {
    data: null,
    timestamp: 0,
    maxAge: 5000 // 5 seconds cache
};

// API Configuration
const API_BASE_URL = window.location.protocol + '//' + window.location.host;

// Function to ensure image paths use the current host
function getFullImagePath(relativePath) {
    // If the path already starts with the current host, return it as is
    if (relativePath.startsWith(API_BASE_URL)) {
        return relativePath;
    }
    // Otherwise, prepend the current host
    return API_BASE_URL + (relativePath.startsWith('/') ? '' : '/') + relativePath;
}

// Initialize the application
document.addEventListener('DOMContentLoaded', () => {
    console.log('Initializing application...');
    checkAuthentication()
        .then(() => {
            // Load folders first
            return fetch(API_BASE_URL + '/folders', {
                credentials: 'include',
                headers: {
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                }
            });
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to load folders');
            }
            return response.json();
        })
        .then(data => {
            // Update all image paths to use the current host
            if (data.folders) {
                data.folders = data.folders.map(folder => {
                    if (folder.screenshots) {
                        folder.screenshots = folder.screenshots.map(screenshot => {
                            screenshot.path = getFullImagePath(screenshot.path);
                            return screenshot;
                        });
                    }
                    return folder;
                });
            }
            
                // Set the header to "All Folders"
                const currentFolderElement = document.getElementById('currentFolder');
                if (currentFolderElement) {
                    currentFolderElement.textContent = 'All Folders';
                }
                
                // Hide the star button
                const starBtn = document.getElementById('starFolderBtn');
                if (starBtn) {
                    starBtn.classList.add('hidden');
                }
            
            // Update the sidebar folder list
            displayFolders(data.folders);
                
                // Display folders grid
            displayFoldersGrid(data.folders);
            
            // Setup event listeners
            setupEventListeners();
        })
        .catch(error => {
            console.error('Initialization error:', error);
            showNotification('Failed to initialize application', 'error');
        });
});

// Check authentication status
async function checkAuthentication() {
    try {
        const response = await fetch(API_BASE_URL + '/check-auth', {
            credentials: 'include',
            headers: {
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            }
        });
        
        if (!response.ok) {
            throw new Error('Authentication check failed');
        }
        
        const data = await response.json();
        if (!data.authenticated) {
            window.location.href = '/';
            return false;
        }
        
        return true;
    } catch (error) {
        console.error('Authentication check failed:', error);
        window.location.href = '/';
        return false;
    }
}

// Add retry logic for failed requests
async function fetchWithRetry(url, options = {}, maxRetries = 3) {
    let lastError;
    
    for (let i = 0; i < maxRetries; i++) {
        try {
            const response = await fetch(url, {
                ...options,
                credentials: 'include',
                headers: {
                    ...options.headers,
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                }
            });
            
            if (response.status === 401) {
                // Redirect to login on authentication failure
                window.location.href = '/';
                return null;
            }
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            return response;
        } catch (error) {
            console.error(`Attempt ${i + 1} failed:`, error);
            lastError = error;
            
            if (i < maxRetries - 1) {
                // Wait before retrying (exponential backoff)
                await new Promise(resolve => setTimeout(resolve, Math.pow(2, i) * 1000));
            }
        }
    }
    
    throw lastError;
}

// Setup event listeners
function setupEventListeners() {
    // Home button
    const homeBtn = document.getElementById('homeBtn');
    if (homeBtn) {
        homeBtn.addEventListener('click', async () => {
            currentFolder = null;
            const currentFolderElement = document.getElementById('currentFolder');
            if (currentFolderElement) {
                currentFolderElement.textContent = 'All Folders';
            }
            const starBtn = document.getElementById('starFolderBtn');
            if (starBtn) {
                starBtn.classList.add('hidden');
            }
            
            try {
                const folders = await loadFolders(true); // Force fetch new data
                displayFoldersGrid(folders);
            } catch (error) {
                console.error('Error loading folders:', error);
                showNotification('Failed to load folders', 'error');
            }
        });
    }

    // Screenshot modal buttons
    const copyBtn = document.getElementById('copyBtn');
    const saveAsBtn = document.getElementById('saveAsBtn');

    if (copyBtn) {
        copyBtn.addEventListener('click', copyToClipboard);
    }

    if (saveAsBtn) {
        saveAsBtn.addEventListener('click', saveScreenshot);
    }

    // New Folder button
    const newFolderBtn = document.getElementById('newFolderBtn');
    const logoutBtn = document.getElementById('logoutBtn');
    const starFolderBtn = document.getElementById('starFolderBtn');

    if (newFolderBtn) {
        newFolderBtn.addEventListener('click', showNewFolderModal);
    }

    // Logout button
    if (logoutBtn) {
        logoutBtn.addEventListener('click', logout);
    }

    // Star folder button
    if (starFolderBtn) {
        starFolderBtn.addEventListener('click', toggleStarFolder);
    }
}

// Load folders with cache busting
async function loadFolders(forceFetch = false) {
    try {
        // Check cache first
        const now = Date.now();
        if (!forceFetch && folderCache.data && (now - folderCache.timestamp < folderCache.maxAge)) {
            displayFolders(folderCache.data.folders);
            return folderCache.data.folders;
        }

        const response = await fetchWithRetry(API_BASE_URL + '/folders');
        if (!response) return [];

        const data = await response.json();
        
        // Update cache
        folderCache.data = data;
        folderCache.timestamp = now;

        displayFolders(data.folders);
        return data.folders;
    } catch (error) {
        console.error('Error loading folders:', error);
        showNotification('Failed to load folders', 'error');
        throw error;
    }
}

// Display folders in sidebar
function displayFolders(folders) {
    const folderList = document.getElementById('folderList');
    if (!folderList) return;
    
    // Create a document fragment for better performance
    const fragment = document.createDocumentFragment();

    if (Array.isArray(folders)) {
        // Sort folders: permanent first, then starred, then alphabetically
        folders.sort((a, b) => {
            if (a.name === 'all') return -1;  // "All Screenshots" always first
            if (b.name === 'all') return 1;
            if (a.is_permanent && !b.is_permanent) return -1;
            if (!a.is_permanent && b.is_permanent) return 1;
            if (a.is_starred && !b.is_starred) return -1;
            if (!a.is_starred && b.is_starred) return 1;
            return (a.display_name || a.name).localeCompare(b.display_name || b.name);
        });

        folders.forEach(folder => {
            const folderName = folder.display_name || folder.name;
            folderTemplate.innerHTML = `
                <div class="folder-item ${
                    currentFolder?.name === folder.name ? 'active' : ''
                } ${folder.is_starred || folder.is_permanent ? 'starred' : ''
                } ${folder.is_permanent ? 'permanent' : ''}"
                     data-folder-name="${folder.name}">
                    <div class="folder-icon">📁</div>
                    <div class="folder-name" title="${folderName}">${folderName}</div>
                    <div class="star-container">
                        ${folder.is_permanent ? 
                          '<span class="permanent-star">★★</span>' :
                          folder.is_starred ? 
                          '<span class="regular-star">★</span>' : 
                          ''}
                    </div>
                </div>
            `;
            
            const folderItem = /** @type {HTMLElement} */ (folderTemplate.content.firstElementChild?.cloneNode(true));
            if (!folderItem) return;

            // Add click handler that works for both mobile and desktop
            folderItem.addEventListener('click', (e) => {
                e.preventDefault();
                if (window.innerWidth <= 768) {
                    handleMobileFolderClick(folder);
                } else {
                    selectFolder(folder);
                }
            });

            fragment.appendChild(folderItem);
        });
    }

    // Clear and update the folder list
    folderList.innerHTML = '';
    folderList.appendChild(fragment);
}

// Select a folder
function selectFolder(folder) {
    currentFolder = folder;
    const currentFolderElement = document.getElementById('currentFolder');
    if (currentFolderElement) {
        const starButton = !folder.is_permanent ? `
            <button class="star-button ml-2" title="${folder.is_starred ? 'Unstar Folder' : 'Star Folder'}">
                <span class="star-icon">${folder.is_starred ? '★' : '☆'}</span>
            </button>
        ` : '';
        currentFolderElement.innerHTML = `
            <div class="flex items-center">
                <span>${folder.display_name || folder.name}</span>
                ${starButton}
            </div>
        `;

        // Add click handler for star button if it exists
        const starBtn = currentFolderElement.querySelector('.star-button');
    if (starBtn) {
            starBtn.addEventListener('click', async () => {
                try {
                    const endpoint = folder.is_starred ? 'unstar' : 'star';
                    const response = await fetch(API_BASE_URL + `/folder/${folder.name}/${endpoint}`, {
                        method: 'POST',
                        credentials: 'include'
                    });

                    if (!response.ok) {
                        const data = await response.json();
                        throw new Error(data.error || 'Failed to update star status');
                    }

                    const data = await response.json();
                    if (data.success) {
                        folder.is_starred = !folder.is_starred;
                        // Update the star button
                        starBtn.innerHTML = `<span class="star-icon">${folder.is_starred ? '★' : '☆'}</span>`;
                        /** @type {HTMLElement} */ (starBtn).title = folder.is_starred ? 'Unstar Folder' : 'Star Folder';
                        
                        // Reload folders to update the order
                        await loadFolders(true);
                    }
                } catch (error) {
                    console.error('Error toggling star status:', error);
                    showNotification('Failed to update star status', 'error');
                }
            });
        }
    }

    // Update active state in folder list
    const folderItems = document.querySelectorAll('.folder-item');
    folderItems.forEach(item => {
        item.classList.remove('active');
        const nameSpan = item.querySelector('.folder-name');
        if (nameSpan && nameSpan.textContent === (folder.display_name || folder.name)) {
            item.classList.add('active');
        }
    });
    
    displayScreenshots(folder.screenshots || []);
}

// Display screenshots in grid
function displayScreenshots(screenshots) {
    const grid = document.getElementById('screenshotGrid');
    if (!grid) return;
    
    // Create a document fragment for better performance
    const fragment = document.createDocumentFragment();

    // Add multi-select button container
    const multiSelectContainer = document.createElement('div');
    multiSelectContainer.className = 'multi-select-container';
    multiSelectContainer.innerHTML = `
        <button class="btn btn-icon" onclick="enterMultiSelectMode()" title="Select Multiple">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M14 0H2C0.9 0 0 0.9 0 2v12c0 1.1 0.9 2 2 2h12c1.1 0 2-0.9 2-2V2c0-1.1-0.9-2-2-2zM7 12L2 7l1.4-1.4L7 9.2l5.6-5.6L14 5l-7 7z"/>
            </svg>
        </button>
    `;
    fragment.appendChild(multiSelectContainer);

    // Create container for screenshots
    const screenshotsContainer = document.createElement('div');
    screenshotsContainer.className = 'screenshots-container';

    screenshots.forEach(screenshot => {
        const imgId = `img-${screenshot.name.replace(/[^a-zA-Z0-9]/g, '-')}`;
        
        // Format the date and time
        const dateTime = screenshot.created ? new Date(screenshot.created) : null;
        const formattedDate = dateTime ? dateTime.toLocaleDateString() : '';
        const formattedTime = dateTime ? dateTime.toLocaleTimeString() : '';
        
        screenshotTemplate.innerHTML = `
            <div class="screenshot-item">
                <div class="image-preview">
                    <img id="${imgId}"
                         alt="${screenshot.name}" 
                         loading="lazy" 
                         crossorigin="use-credentials">
                    <div class="content-overlay">
                        <div class="screenshot-info">${formattedDate} ${formattedTime}</div>
                </div>
                ${isMultiSelectMode ? `
                    <div class="absolute top-2 left-2 w-6 h-6 rounded border-2 border-white checkbox-overlay"></div>
                ` : ''}
                    <div class="action-buttons">
                        <button class="btn-action" onclick="copyToClipboard('${screenshot.path}')" title="Copy to Clipboard">
                            📋
                        </button>
                        <button class="btn-action" onclick="saveScreenshot('${screenshot.path}', '${screenshot.name}')" title="Save As">
                            💾
                        </button>
                        <div class="dropdown">
                            <button class="btn-action" onclick="toggleMenu('${screenshot.name}', event)" title="More Options">⋮</button>
                            <div class="dropdown-menu" id="menu-${screenshot.name}">
                                <button class="dropdown-item" onclick="viewScreenshot('${screenshot.path}', '${screenshot.name}', '${formattedDate}')">
                                    View
                                </button>
                                <button class="dropdown-item" onclick="handleMoveOrCopy('move', '${screenshot.name}')">
                                    Move to Folder
                                </button>
                                <button class="dropdown-item" onclick="handleMoveOrCopy('copy', '${screenshot.name}')">
                                    Copy to Folder
                                </button>
                                <div class="dropdown-divider"></div>
                                <button class="dropdown-item text-red-500" onclick="handleDeleteScreenshot('${screenshot.name}')">
                                    Delete
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="name-label" title="${screenshot.name}">${screenshot.name}</div>
            </div>
        `;
        
        const item = /** @type {HTMLElement} */ (screenshotTemplate.content.firstElementChild?.cloneNode(true));
        if (!item) return;

        // Load the image
        const img = /** @type {HTMLImageElement} */ (item.querySelector(`#${imgId}`));
        if (img) {
            loadImage(screenshot.path, img, screenshot.name);
        }

        // Add click handler for multi-select mode
        item.addEventListener('click', (e) => {
            if (isMultiSelectMode) {
                e.preventDefault();
                e.stopPropagation();
                
                if (selectedScreenshots.has(screenshot.name)) {
                    selectedScreenshots.delete(screenshot.name);
                    item.classList.remove('screenshot-selected');
                } else {
                    selectedScreenshots.add(screenshot.name);
                    item.classList.add('screenshot-selected');
                }
                
                showBulkActionsMenu();
            } else {
                const target = e.target;
                if (target instanceof Element && !target.closest('.btn-action') && !target.closest('.dropdown')) {
                    currentScreenshot = {
                        path: screenshot.path,
                        name: screenshot.name,
                        date: screenshot.date
                    };
                    viewScreenshot(screenshot.path, screenshot.name, screenshot.date);
                }
            }
        });

        screenshotsContainer.appendChild(item);
    });

    fragment.appendChild(screenshotsContainer);

    // Clear and update the grid in one operation
    grid.innerHTML = '';
    grid.appendChild(fragment);
}

// Simple menu toggle function
function toggleMenu(name, event) {
    if (!event) return;
    event.stopPropagation();
    
    const menu = document.getElementById('menu-' + name);
    if (!menu) return;

    // If this menu is already shown, just hide it
    if (menu.classList.contains('show')) {
        menu.classList.remove('show');
        return;
    }
    
    // Close all other menus first
    document.querySelectorAll('.dropdown-menu').forEach(menu => {
        menu.classList.remove('show');
    });
    
    // Position and show this menu
    const button = /** @type {HTMLElement} */ (event.currentTarget);
    if (!button) return;
    
    const rect = button.getBoundingClientRect();
    menu.style.left = `${rect.left}px`;
    menu.style.top = `${rect.bottom + 2}px`;
    
    // Ensure menu doesn't go off-screen
    const menuRect = menu.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    
    if (menuRect.right > viewportWidth) {
        menu.style.left = `${viewportWidth - menuRect.width - 4}px`;
    }
    
    if (menuRect.bottom > viewportHeight) {
        menu.style.top = `${rect.top - menuRect.height - 2}px`;
    }
    
    menu.classList.add('show');
}

// Close menus when clicking outside
document.addEventListener('click', function(event) {
    const target = /** @type {HTMLElement} */ (event.target);
    if (!target) return;
    
    if (!target.closest('.dropdown-menu') && !target.closest('.btn-action')) {
        document.querySelectorAll('.dropdown-menu').forEach(menu => {
            menu.classList.remove('show');
        });
    }
});

// Close screenshot modal
function closeScreenshotModal() {
    const modal = document.getElementById('screenshotModal');
    const content = document.getElementById('screenshotModalContent');
    if (modal) {
        modal.classList.remove('show');
        modal.classList.add('hidden');
    }
    if (content) {
        content.style.width = '';
        content.style.height = '';
        // Clean up image
        const img = content.querySelector('img');
        if (img) {
            const url = imageCache.get(img.src);
            if (url) {
                URL.revokeObjectURL(url);
                imageCache.delete(img.src);
            }
        }
        content.innerHTML = '';
    }
    if (currentScreenshot) {
        const url = imageCache.get(currentScreenshot.path);
        if (url) {
            URL.revokeObjectURL(url);
            imageCache.delete(currentScreenshot.path);
        }
        currentScreenshot = null;
    }
}

// View screenshot
function viewScreenshot(path, name, date) {
    const modal = document.getElementById('screenshotModal');
    const content = document.getElementById('screenshotModalContent');
    const title = document.getElementById('screenshotModalTitle');
    
    if (!modal || !content || !title) return;
    
    currentScreenshot = { path, name, date };
    title.textContent = name;
    
    // Create image element
    const img = document.createElement('img');
    img.style.maxWidth = '100%';
    img.style.maxHeight = 'calc(90vh - 100px)';
    img.style.objectFit = 'contain';
    
    // Show loading state
    content.innerHTML = '<div class="loading">Loading...</div>';
    
    // Load image
    loadImage(path, img, name)
        .then(() => {
            content.innerHTML = '';
            content.appendChild(img);
        })
        .catch(error => {
            console.error('Error loading image:', error);
            content.innerHTML = '<div class="error">Failed to load image</div>';
        });
    
    // Show modal
    modal.classList.remove('hidden');
    modal.classList.add('show');
}

// Display a specific folder
async function displayFolder(folder) {
    if (!folder) return;
    
    currentFolder = folder;
    
    // Update current folder display
    const currentFolderElement = document.getElementById('currentFolder');
    if (currentFolderElement) {
        currentFolderElement.textContent = folder.display_name || folder.name;
    }
    
    // Update folder list selection
    const folderItems = document.querySelectorAll('.folder-item');
    folderItems.forEach(item => {
        const folderItem = /** @type {HTMLElement} */ (item);
        folderItem.classList.remove('active');
        if (folderItem.dataset.folder === folder.name) {
            folderItem.classList.add('active');
        }
    });
    
    // Display the folder's screenshots
    const grid = document.getElementById('screenshotGrid');
    if (grid) {
        displayScreenshots(folder.screenshots || []);
    }
    
    // Always hide the star button - we're not using it anymore
    const starFolderBtn = document.getElementById('starFolderBtn');
    if (starFolderBtn) {
        starFolderBtn.classList.add('hidden');
    }
}

// Create new folder
async function createFolder() {
    const nameInput = /** @type {HTMLInputElement} */ (document.getElementById('newFolderName'));
    if (!nameInput) {
        console.error('New folder name input not found');
        return;
    }

    const name = nameInput.value.trim();
    if (!name) {
        showNotification('Folder name is required', 'error');
        return;
    }

    try {
        const response = await fetch(API_BASE_URL + '/folder', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name }),
            credentials: 'include'
        });

        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || 'Failed to create folder');
        }

        showNotification('Folder created successfully');
        
        // Close the modal
        closeModal();
        
        // Refresh the folders list
        const folders = await loadFolders(true);
        
        // Switch to the new folder
        const newFolder = folders.find(f => f.name === name);
        if (newFolder) {
            // Hide the star button since this is a new folder
            const starFolderBtn = document.getElementById('starFolderBtn');
            if (starFolderBtn) {
                starFolderBtn.classList.add('hidden');
            }
            displayFolder(newFolder);
        }
    } catch (error) {
        console.error('Error creating folder:', error);
        showNotification(error.message || 'Failed to create folder', 'error');
    }
}

// Show modal for new folder
function showNewFolderModal() {
    const modalContent = `
        <div class="modal-content" style="width: 300px;">
            <div class="modal-title">
                <span>Create New Folder</span>
                <button class="close-modal">×</button>
            </div>
            <div class="modal-body p-4">
                <div class="mb-4">
                    <label for="newFolderName" class="block mb-2">Folder Name:</label>
                    <input type="text" id="newFolderName" class="w-full px-2 py-1 border" 
                           placeholder="Enter folder name">
                </div>
                <div class="flex justify-end space-x-2">
                    <button class="btn close-modal">Cancel</button>
                    <button onclick="createFolder()" class="btn btn-primary">Create</button>
                </div>
            </div>
        </div>
    `;

    const modal = document.getElementById('modal');
    if (modal) {
        modal.innerHTML = modalContent;
        modal.classList.remove('hidden');

        // Add event listeners for close buttons
        const closeButtons = modal.querySelectorAll('.close-modal');
        closeButtons.forEach(button => {
            button.addEventListener('click', closeModal);
        });

        // Focus the input field
        const input = document.getElementById('newFolderName');
        if (input) {
            input.focus();
            // Handle enter key
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    createFolder();
                }
            });
        }
    }
}

// Toggle star status for current folder
async function toggleStarFolder() {
    if (!currentFolder || currentFolder.is_permanent) return;

    const starBtn = document.getElementById('starFolderBtn');
    if (!starBtn) return;

    try {
        const endpoint = currentFolder.is_starred ? 'unstar' : 'star';
        const response = await fetch(API_BASE_URL + `/folder/${currentFolder.name}/${endpoint}`, {
            method: 'POST',
            credentials: 'include'
        });

        if (!response.ok) {
        const data = await response.json();
            throw new Error(data.error || 'Failed to update star status');
        }

        const data = await response.json();

        if (data.success) {
            currentFolder.is_starred = !currentFolder.is_starred;
            
            // Update star button
            starBtn.innerHTML = `
                <span class="star-icon text-2xl text-yellow-500">${currentFolder.is_starred ? '★' : '☆'}</span>
            `;
            
            // Update the folder list to reflect the new star status
            const folderItem = document.querySelector(`.folder-item .folder-name[title="${currentFolder.display_name || currentFolder.name}"]`)?.closest('.folder-item');
            if (folderItem) {
                if (currentFolder.is_starred) {
                    folderItem.classList.add('starred');
                } else {
                    folderItem.classList.remove('starred');
                }
            }
            
            // Reload folders to update the order
            await loadFolders();
        } else {
            throw new Error('Failed to update star status');
        }
    } catch (error) {
        console.error('Error toggling star status:', error);
        showNotification('Failed to update star status', 'error');
    }
}

// Handle screenshot deletion
async function deleteScreenshot(filename, isBulkOperation = false) {
    if (!filename) {
        console.error('No filename provided for deletion');
        return;
    }
    
    if (isBulkOperation || confirm('Are you sure you want to delete this screenshot?')) {
        // Extract the folder name from the current screenshot's path
        let folderName = 'all';  // Default to 'all' if no folder is found
        
        if (currentFolder?.name) {
            folderName = currentFolder.name;
        } else if (currentScreenshot?.path) {
            // Extract folder from path (format: /image/folder/filename)
            const pathParts = currentScreenshot.path.split('/');
            if (pathParts.length >= 3) {
                folderName = pathParts[2];  // Get the folder name from the path
            }
        }
        
        const deleteUrl = API_BASE_URL + `/delete/${folderName}/${filename}`;
        
        try {
            const response = await fetch(deleteUrl, {
                method: 'DELETE',
                credentials: 'include'
            });
            
            if (response.status === 401) {
                window.location.href = '/';
                return;
            }
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || 'Failed to delete screenshot');
            }
            
            if (!isBulkOperation) {
                closeScreenshotModal();
                showNotification('Screenshot deleted successfully');
                // Refresh the view for single deletions
                await refreshCurrentView();
            }
            
            return true;
        } catch (error) {
            console.error('Error during delete operation:', error);
            if (!isBulkOperation) {
                showNotification('Failed to delete screenshot: ' + error.message, 'error');
            }
            throw error;
        }
    }
}

// Delete folder
async function deleteFolder(folderName) {
    if (!confirm('Are you sure you want to delete this folder and all its contents?')) return;

    try {
        const response = await fetch(API_BASE_URL + `/folder/${folderName}`, {
            method: 'DELETE',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (response.status === 405) {
            throw new Error('Method not allowed. This folder cannot be deleted.');
        }

        const data = await response.json();

        if (response.ok) {
            if (currentFolder && currentFolder.name === folderName) {
                currentFolder = null;
                const currentFolderElement = document.getElementById('currentFolder');
                if (currentFolderElement) {
                    currentFolderElement.textContent = 'All Screenshots';
                }
                const grid = document.getElementById('screenshotGrid');
                if (grid) {
                    grid.innerHTML = '';
                }
            }
            await loadFolders();
            showNotification('Folder deleted successfully');
        } else {
            showNotification(data.error || 'Failed to delete folder', 'error');
        }
    } catch (error) {
        console.error('Error deleting folder:', error);
        showNotification(error.message || 'Failed to delete folder', 'error');
    }
}

// Logout
async function logout() {
    try {
        await fetch(API_BASE_URL + '/logout', {
            credentials: 'include'
        });
        window.location.href = '/';
    } catch (error) {
        console.error('Logout failed:', error);
        showNotification('Logout failed', 'error');
    }
}

// Modal functions
function showModal(title, content) {
    const modal = document.getElementById('modal');
    const modalTitle = document.getElementById('modalTitle');
    const modalContent = document.getElementById('modalContent');

    if (!modal || !modalTitle || !modalContent) {
        console.error('Modal elements not found');
        return;
    }

    modalTitle.textContent = title;
    modalContent.innerHTML = content;
    modal.classList.remove('hidden');
}

function closeModal() {
    const modal = document.getElementById('modal');
    if (modal) {
        modal.classList.add('hidden');
    }
}

// Notification functions
function showNotification(message, type = 'success') {
    const notification = document.getElementById('notification');
    const text = document.getElementById('notificationText');
    
    if (!notification || !text) {
        console.error('Notification elements not found');
        return;
    }
    
    text.textContent = message;
    notification.classList.remove('hidden');
    notification.classList.add(type === 'error' ? 'bg-red-500' : 'bg-green-500');

    setTimeout(() => {
        if (notification) {
            notification.classList.add('hidden');
        }
    }, 3000);
}

// Initialize event listeners for modals
document.addEventListener('DOMContentLoaded', function() {
    // Add event listeners for move modal close buttons
    const moveModal = document.getElementById('moveModal');
    if (!moveModal) return;

    // Add event listeners to all close buttons
    const closeButtons = moveModal.querySelectorAll('.close-move-modal');
    closeButtons.forEach(button => {
        button.addEventListener('click', closeMoveModal);
    });

    // Add event listener for confirm button
    const confirmBtn = document.getElementById('moveConfirmBtn');
    if (confirmBtn) {
        confirmBtn.addEventListener('click', moveOrCopyScreenshot);
    }
    
    // Ensure modal is hidden initially
    moveModal.classList.add('hidden');
    currentScreenshot = null;
    delete moveModal.dataset.operation;
});

// Handle move or copy operation
function handleMoveOrCopy(operation, name) {
    console.log('handleMoveOrCopy called:', { operation, name });
    
    if (!name) {
        console.error('No screenshot name provided for move/copy operation');
        showNotification('No screenshot selected', 'error');
        return;
    }

    // Show the move modal
    showMoveModal(operation, name);
}

// Show the move/copy modal
function showMoveModal(operation, screenshot) {
    console.log('Showing move modal:', { operation, screenshot });
    
    if (!screenshot) {
        console.error('No screenshot provided for move/copy operation');
        showNotification('No screenshot selected', 'error');
        return;
    }

    const modal = document.getElementById('moveModal');
    const foldersList = document.getElementById('foldersList');
    const modalTitle = document.getElementById('moveModalTitle');
    const confirmBtn = /** @type {HTMLButtonElement} */ (document.getElementById('moveConfirmBtn'));
    
    if (!modal || !foldersList || !modalTitle || !confirmBtn) {
        console.error('Missing modal elements');
        return;
    }

    // Set the title based on whether it's a single screenshot or multiple
    const isMultiple = Array.isArray(screenshot);
    modalTitle.textContent = `${operation === 'move' ? 'Move' : 'Copy'} ${isMultiple ? 'Screenshots' : 'Screenshot'}`;

    // Store the operation type and screenshot info in the modal's dataset
    modal.dataset.operation = operation;
    modal.dataset.screenshots = JSON.stringify(isMultiple ? screenshot : [screenshot]);

    // Disable confirm button initially
    confirmBtn.disabled = true;

    // Close any open dropdowns
    document.querySelectorAll('.dropdown-menu').forEach(menu => {
        menu.classList.remove('show');
    });
    
    // Show loading state
    foldersList.innerHTML = '<div class="p-4 text-center">Loading folders...</div>';
    modal.classList.remove('hidden');
    
    // Load folders for move/copy operation
    fetch(API_BASE_URL + '/folders', {
        credentials: 'include'
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Failed to load folders');
        }
        return response.json();
    })
    .then(data => {
        if (!data.folders || !Array.isArray(data.folders)) {
            throw new Error('Invalid folder data received');
        }

        // Filter out the current folder and the "All Screenshots" folder
        const filteredFolders = data.folders.filter(folder => {
            if (folder.name === 'all') return false;
            if (operation === 'move' && currentFolder && folder.name === currentFolder.name) return false;
            return true;
        });

        if (filteredFolders.length === 0) {
            foldersList.innerHTML = '<div class="p-4 text-center">No available folders to move to. Create a new folder first.</div>';
            return;
        }

            foldersList.innerHTML = filteredFolders.map(folder => `
            <div class="folder-option p-2 hover:bg-gray-100 cursor-pointer">
                    <input type="radio" name="targetFolder" value="${folder.name}" 
                       class="radio-input mr-2">
                <span class="folder-name">${folder.display_name || folder.name}</span>
                </div>
            `).join('');

            // Add click handlers for folder options
            const options = foldersList.querySelectorAll('.folder-option');
            options.forEach(option => {
                option.addEventListener('click', () => {
                    const radio = /** @type {HTMLInputElement} */ (option.querySelector('input[type="radio"]'));
                    if (radio) {
                        // Uncheck all other radios
                        const allRadios = foldersList.querySelectorAll('input[type="radio"]');
                        allRadios.forEach(r => {
                            const radioInput = /** @type {HTMLInputElement} */ (r);
                            radioInput.checked = false;
                        });
                        // Check this radio
                        radio.checked = true;
                        confirmBtn.disabled = false;
                    }
                });
            });
    })
    .catch(error => {
        console.error('Error loading folders:', error);
        foldersList.innerHTML = `<div class="p-4 text-center text-red-500">Error: ${error.message}</div>`;
        showNotification('Failed to load folders', 'error');
    });
}

// Move or copy screenshot
async function moveOrCopyScreenshot() {
    const modal = document.getElementById('moveModal');
    if (!modal) return;

    const operation = modal.dataset.operation;
    const screenshots = JSON.parse(modal.dataset.screenshots || '[]');
    const selectedFolder = /** @type {HTMLInputElement} */ (document.querySelector('input[name="targetFolder"]:checked'));

    if (!screenshots.length || !selectedFolder) {
        showNotification('Please select a target folder', 'error');
        return;
    }

    const confirmBtn = /** @type {HTMLButtonElement} */ (document.getElementById('moveConfirmBtn'));
    if (confirmBtn) {
        confirmBtn.disabled = true;
    }

    const total = screenshots.length;
    let completed = 0;
    let failed = 0;

    // Show progress notification
    const notification = document.createElement('div');
    notification.id = 'moveProgressNotification';
    notification.className = 'fixed bottom-4 right-4 bg-gray-800 text-white px-4 py-2 rounded shadow-lg z-50';
    notification.innerHTML = `${operation === 'move' ? 'Moving' : 'Copying'} screenshots: 0/${total}`;
    document.body.appendChild(notification);

    try {
        // Process in batches of 5
        const batchSize = 5;
        for (let i = 0; i < screenshots.length; i += batchSize) {
            const batch = screenshots.slice(i, i + batchSize);
            const promises = batch.map(async (screenshot) => {
                try {
                    // If we're in the "all" view, find the actual source folder from the screenshot path
                    let sourceFolder = currentFolder ? currentFolder.name : 'all';
                    
                    if (sourceFolder === 'all') {
                        const img = /** @type {HTMLImageElement} */ (document.querySelector(`img[alt="${screenshot}"]`));
                        if (img) {
                            const path = img.src;
                            // Extract folder from path (format: /image/user_1/folder/filename or /image/user_1\folder\filename)
                            const pathParts = path.split(/[/\\]/); // Split on both forward and backward slashes
                            if (pathParts.length >= 4) {
                                // The folder should be after 'user_1' in the path
                                const userIndex = pathParts.findIndex(part => part.startsWith('user_'));
                                if (userIndex !== -1 && pathParts[userIndex + 1]) {
                                    sourceFolder = pathParts[userIndex + 1];
                                }
                            }
                        }
                    }

            const requestData = {
                        source_folder: sourceFolder,
                target_folder: selectedFolder.value,
                        filename: screenshot,
                operation: operation
            };

                    console.log('Moving/copying screenshot:', requestData);

                    const response = await fetch(API_BASE_URL + '/move_screenshot', {
                method: 'POST',
                headers: {
                            'Content-Type': 'application/json',
                            'Accept': 'application/json'
                },
                body: JSON.stringify(requestData),
                credentials: 'include'
            });

            if (!response.ok) {
                        const errorData = await response.json();
                        throw new Error(errorData.error || 'Failed to process screenshot');
                    }

                    completed++;
                } catch (error) {
                    console.error(`Error processing ${screenshot}:`, error);
                    failed++;
                } finally {
                    const notif = document.getElementById('moveProgressNotification');
                    if (notif) {
                        notif.innerHTML = `${operation === 'move' ? 'Moving' : 'Copying'} screenshots: ${completed + failed}/${total}`;
                    }
                }
            });

            await Promise.all(promises);
        }

        // Remove progress notification
        const notif = document.getElementById('moveProgressNotification');
        if (notif && notif.parentNode) {
            notif.parentNode.removeChild(notif);
        }

        // Show final result
        if (failed > 0) {
            showNotification(`${operation === 'move' ? 'Moved' : 'Copied'} ${completed} screenshots, ${failed} failed`, 'error');
        } else {
            showNotification(`Successfully ${operation === 'move' ? 'moved' : 'copied'} ${completed} screenshots`);
        }

        closeMoveModal();
        closeScreenshotModal();
        
        // Refresh the view
        await refreshCurrentView();
        
        if (isMultiSelectMode) {
            exitMultiSelectMode();
        }
    } catch (error) {
        console.error(`Error during ${operation}:`, error);
        showNotification(`Failed to ${operation} screenshots: ${error.message}`, 'error');
    } finally {
        if (confirmBtn) {
            confirmBtn.disabled = false;
        }
        // Ensure notification is removed
        const notif = document.getElementById('moveProgressNotification');
        if (notif && notif.parentNode) {
            notif.parentNode.removeChild(notif);
        }
    }
}

// Close move modal
function closeMoveModal() {
    const modal = document.getElementById('moveModal');
    if (modal) {
        modal.classList.add('hidden');
        // Clear modal data
        delete modal.dataset.operation;
        delete modal.dataset.screenshots;
    }
}

// Copy to clipboard
async function copyToClipboard(path) {
    const screenshotPath = path || (currentScreenshot ? currentScreenshot.path : null);
    if (!screenshotPath) return;

    try {
        const response = await fetch(screenshotPath, {
            credentials: 'include',
            headers: {
                'Accept': 'image/png'
            }
        });
        
        if (!response.ok) {
            throw new Error('Failed to fetch image');
        }
        
        const blob = await response.blob();
        const pngBlob = new Blob([blob], { type: 'image/png' });
        
        try {
            await navigator.clipboard.write([
                new ClipboardItem({
                    'image/png': pngBlob
                })
            ]);
            showNotification('Screenshot copied to clipboard');
        } catch (err) {
            // Fallback for browsers that don't support clipboard.write
            const img = document.createElement('img');
            img.src = URL.createObjectURL(pngBlob);
            document.body.appendChild(img);
            const selection = window.getSelection();
            if (!selection) {
                throw new Error('Could not get selection');
            }
            const range = document.createRange();
            range.selectNode(img);
            selection.removeAllRanges();
            selection.addRange(range);
            document.execCommand('copy');
            document.body.removeChild(img);
            URL.revokeObjectURL(img.src);
            showNotification('Screenshot copied to clipboard');
        }
    } catch (error) {
        console.error('Error copying to clipboard:', error);
        showNotification('Failed to copy to clipboard', 'error');
    }
}

// Save screenshot
async function saveScreenshot(path, name) {
    const screenshot = {
        path: path || (currentScreenshot ? currentScreenshot.path : null),
        name: name || (currentScreenshot ? currentScreenshot.name : null)
    };

    if (!screenshot.path || !screenshot.name) return;

    try {
        const response = await fetch(screenshot.path, {
            credentials: 'include',
            headers: {
                'Accept': 'image/png'
            }
        });
        
        if (!response.ok) {
            throw new Error('Failed to fetch image');
        }
        
        const blob = await response.blob();
        // Ensure we're saving as PNG
        const pngBlob = new Blob([blob], { type: 'image/png' });
        const url = window.URL.createObjectURL(pngBlob);
        const a = document.createElement('a');
        a.href = url;
        a.download = screenshot.name.endsWith('.png') ? screenshot.name : `${screenshot.name}.png`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        showNotification('Screenshot saved successfully');
    } catch (error) {
        console.error('Error saving screenshot:', error);
        showNotification('Failed to save screenshot', 'error');
    }
}

// Add upload functionality
document.addEventListener('DOMContentLoaded', function() {
    const uploadBtn = document.getElementById('uploadBtn');
    if (uploadBtn) {
        uploadBtn.addEventListener('click', function() {
            // Create a file input element
            const fileInput = document.createElement('input');
            fileInput.type = 'file';
            fileInput.accept = 'image/*';
            fileInput.multiple = true; // Allow multiple files
            
            fileInput.addEventListener('change', async function() {
                if (!fileInput.files || fileInput.files.length === 0) return;
                
                const files = Array.from(fileInput.files);
                console.log('Files selected:', files);
                
                for (const file of files) {
                    const formData = new FormData();  // Create new FormData for each file
                    formData.append('file', file);
                    
                    if (currentFolder) {
                        formData.append('folder', currentFolder.name);
                    }
                    
                    try {
                        console.log('Uploading file:', file.name);
                        const response = await fetch(API_BASE_URL + '/upload', {
                            method: 'POST',
                            body: formData,
                            credentials: 'include'
                        });
                        
                        if (!response.ok) {
                            const data = await response.json();
                            throw new Error(data.error || 'Upload failed');
                        }
                        
                        const data = await response.json();
                        showNotification(`${file.name} uploaded successfully`);
                        
                        // Refresh the view
                        await refreshCurrentView();
                        
                    } catch (error) {
                        console.error('Upload error:', error);
                        showNotification(`Failed to upload ${file.name}: ${error.message}`, 'error');
                    }
                }
            });
            
            // Trigger the file input click
            fileInput.click();
        });
    }
});

// Screenshot actions
function downloadScreenshot() {
    if (!currentScreenshot) return;
    
    const link = document.createElement('a');
    link.href = currentScreenshot.path;
    link.download = currentScreenshot.name;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    // Close the dropdown
    const dropdown = document.getElementById('modalDropdown');
    if (dropdown) {
        dropdown.classList.add('hidden');
    }
}

// Handle delete screenshot
async function handleDeleteScreenshot(name) {
    if (!name) {
        console.error('No screenshot name provided for deletion');
        showNotification('Screenshot name not found', 'error');
        return;
    }
    
    try {
        // Get the current folders data before deletion
        const foldersResponse = await fetch(API_BASE_URL + '/folders', {
            credentials: 'include'
        });
        const foldersData = await foldersResponse.json();
        
        // Perform the deletion
        await deleteScreenshot(name);
        
        // Update the sidebar folder list with the existing data first
        displayFolders(foldersData.folders);
        
        // Then fetch new data and update again
        const updatedFoldersResponse = await fetch(API_BASE_URL + '/folders', {
            credentials: 'include'
        });
        const updatedFolders = await updatedFoldersResponse.json();
        
        // Update the sidebar folder list with new data
        displayFolders(updatedFolders.folders);
        
        // If we're in a specific folder, update its contents
        const folderName = currentFolder?.name;
        if (folderName) {
            const updatedFolder = updatedFolders.folders.find(f => f.name === folderName);
            if (updatedFolder) {
                currentFolder = updatedFolder;
                displayScreenshots(updatedFolder.screenshots || []);
            }
        } else {
            // If we're in the "All Screenshots" view, display the folders grid
            displayFoldersGrid(updatedFolders.folders);
        }
    } catch (error) {
        console.error('Error handling screenshot deletion:', error);
        showNotification('Failed to delete screenshot', 'error');
    }
}

// Add new function to get a random screenshot from an array
function getRandomScreenshot(screenshots) {
    if (!screenshots || screenshots.length === 0) return null;
    const randomIndex = Math.floor(Math.random() * screenshots.length);
    return screenshots[randomIndex];
}

// Add new function to display folders in a grid
function displayFoldersGrid(folders) {
    const grid = document.getElementById('screenshotGrid');
    if (!grid) return;
    
    // Clear existing content
    grid.innerHTML = '';

    if (!Array.isArray(folders)) {
        console.error('Folders data is not an array:', folders);
        return;
    }

    // Create a document fragment for better performance
    const fragment = document.createDocumentFragment();

    // Create a container for the horizontal folder list
    const folderListContainer = document.createElement('div');
    folderListContainer.className = 'horizontal-folder-list';

    folders.forEach(folder => {
        const folderName = folder.display_name || folder.name;
        const folderDiv = document.createElement('div');
        folderDiv.className = 'folder-grid-item';
        
        // Calculate the number of screenshots
        const screenshotCount = folder.screenshots ? folder.screenshots.length : 0;
        
        // Get a preview screenshot if available
        const previewScreenshot = folder.screenshots && folder.screenshots.length > 0 
            ? folder.screenshots[0] 
            : null;

        folderDiv.innerHTML = `
            <div class="folder-preview">
                ${previewScreenshot ? `
                    <img src="${previewScreenshot.path}" 
                         alt="Preview" 
                         class="preview-image"
                         loading="lazy"
                         crossorigin="use-credentials">
                ` : ''}
                <div class="folder-icon">📁</div>
                    </div>
            <div class="folder-info">
                <div class="folder-name" title="${folderName}">${folderName}</div>
                <div class="folder-stats">${screenshotCount} screenshot${screenshotCount !== 1 ? 's' : ''}</div>
                        </div>
            ${folder.is_permanent ? '<div class="permanent-badge">★★</div>' : 
              folder.is_starred ? '<div class="star-badge">★</div>' : ''}
            <div class="folder-tooltip">
                <div class="tooltip-content">
                    <strong>${folderName}</strong><br>
                    ${screenshotCount} screenshot${screenshotCount !== 1 ? 's' : ''}<br>
                    ${folder.is_permanent ? 'System Folder' : 
                      folder.is_starred ? 'Starred Folder' : 'Regular Folder'}
                </div>
            </div>
        `;
        
        folderDiv.addEventListener('click', () => selectFolder(folder));
        folderListContainer.appendChild(folderDiv);
    });

    fragment.appendChild(folderListContainer);
    grid.appendChild(fragment);
}

// Add new function for bulk actions menu
function showBulkActionsMenu() {
    // Remove existing bulk menu if any
    const existingMenu = document.getElementById('bulkActionsMenu');
    if (existingMenu) {
        existingMenu.remove();
    }

    const menu = document.createElement('div');
    menu.id = 'bulkActionsMenu';
    menu.innerHTML = `
        <span>${selectedScreenshots.size} selected</span>
        <button class="btn" onclick="handleBulkMove()">Move</button>
        <button class="btn" onclick="handleBulkCopy()">Copy</button>
        <button class="btn" onclick="handleBulkDelete()">Delete</button>
        <button class="btn" onclick="exitMultiSelectMode()">Cancel</button>
    `;

    document.body.appendChild(menu);
}

// Add function to handle entering multi-select mode
function enterMultiSelectMode() {
    isMultiSelectMode = true;
    selectedScreenshots.clear();
    const grid = document.getElementById('screenshotGrid');
    if (grid) {
        grid.classList.add('multi-select-mode');
    }
    showBulkActionsMenu();
}

// Add function to handle exiting multi-select mode
function exitMultiSelectMode() {
    isMultiSelectMode = false;
    selectedScreenshots.clear();
    const grid = document.getElementById('screenshotGrid');
    if (grid) {
        grid.classList.remove('multi-select-mode');
        // Remove selection indicators
        grid.querySelectorAll('.screenshot-selected').forEach(el => {
            el.classList.remove('screenshot-selected');
        });
    }
    const menu = document.getElementById('bulkActionsMenu');
    if (menu) {
        menu.remove();
    }
}

// Add bulk action handlers
async function handleBulkMove() {
    if (selectedScreenshots.size === 0) return;
    showMoveModal('move', Array.from(selectedScreenshots));
}

async function handleBulkCopy() {
    if (selectedScreenshots.size === 0) return;
    showMoveModal('copy', Array.from(selectedScreenshots));
}

async function handleBulkDelete() {
    if (selectedScreenshots.size === 0) return;
    
    if (confirm(`Are you sure you want to delete ${selectedScreenshots.size} screenshots?`)) {
        const total = selectedScreenshots.size;
        let completed = 0;
        let failed = 0;
        
        // Show progress notification
        const notification = document.createElement('div');
        notification.id = 'deleteProgressNotification';
        notification.className = 'fixed bottom-4 right-4 bg-gray-800 text-white px-4 py-2 rounded shadow-lg z-50';
        notification.innerHTML = `Deleting screenshots: 0/${total}`;
        document.body.appendChild(notification);
        
        // Process in batches of 5
        const batchSize = 5;
        const screenshots = Array.from(selectedScreenshots);
        
        try {
            for (let i = 0; i < screenshots.length; i += batchSize) {
                const batch = screenshots.slice(i, i + batchSize);
                const promises = batch.map(filename => 
                    deleteScreenshot(filename, true)
                        .then(() => completed++)
                        .catch(() => failed++)
                        .finally(() => {
                            const notif = document.getElementById('deleteProgressNotification');
                            if (notif) {
                                notif.innerHTML = `Deleting screenshots: ${completed + failed}/${total}`;
                            }
                        })
                );
                
            await Promise.all(promises);
            }
        } finally {
            // Remove progress notification safely
            const notif = document.getElementById('deleteProgressNotification');
            if (notif && notif.parentNode) {
                notif.parentNode.removeChild(notif);
            }
        }
        
        // Show final result
        if (failed > 0) {
            showNotification(`Deleted ${completed} screenshots, ${failed} failed`, 'error');
        } else {
            showNotification(`Successfully deleted ${completed} screenshots`);
        }
        
        exitMultiSelectMode();
        
        // Refresh the view only once after all operations are complete
        await refreshCurrentView();
    }
}

// Add function to refresh the current view
async function refreshCurrentView() {
    try {
        const foldersData = await loadFolders(true); // Force fetch new data
        
        // Update the main view
        const folderName = currentFolder?.name;
        if (folderName) {
            const updatedFolder = foldersData.find(f => f.name === folderName);
            if (updatedFolder) {
                currentFolder = updatedFolder;
                displayScreenshots(updatedFolder.screenshots || []);
            }
        } else {
            // If we're in the "All Screenshots" view, display the folders grid
            displayFoldersGrid(foldersData);
        }
    } catch (error) {
        console.error('Error refreshing view:', error);
        showNotification('Failed to refresh view', 'error');
    }
}

// Image loading function
async function loadImage(path, img, name) {
    const fullPath = getFullImagePath(path);
    
    // Set loading state
    img.style.opacity = '0.3';
    
    try {
        const response = await fetch(fullPath, {
            credentials: 'include',
            headers: {
                'Accept': 'image/png'
            }
        });
        
        if (!response.ok) throw new Error('Failed to load image');
        
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        
        // Set the image source and show it
        img.onload = () => {
            img.style.opacity = '1';
        };
        img.src = url;
        
        // Cache the URL
        imageCache.set(fullPath, url);
        
    } catch (error) {
        console.error('Error loading image:', error);
        handleImageError(img, name);
    }
}

// Handle image error
function handleImageError(img, name) {
    console.error(`Error loading image for ${name}`);
    img.style.opacity = '1';
    img.style.background = '#f0f0f0';
    img.style.display = 'flex';
    img.style.alignItems = 'center';
    img.style.justifyContent = 'center';
    img.style.color = '#666';
    img.style.fontSize = '14px';
    img.style.padding = '12px';
    img.style.textAlign = 'center';
    img.alt = 'Failed to load image';
    img.src = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxsaW5lIHgxPSIxOCIgeTE9IjYiIHgyPSI2IiB5Mj0iMTgiPjwvbGluZT48bGluZSB4MT0iNiIgeTE9IjYiIHgyPSIxOCIgeTI9IjE4Ij48L2xpbmU+PC9zdmc+';
}

// Upload to website
async function uploadToWebsite(file, folder = '') {
    // Close only the current window (screenshot window) immediately after clicking upload
    window.close();

    try {
        const formData = new FormData();
        formData.append('file', file);
        if (folder) {
            formData.append('folder', folder);
        }

        const response = await fetch(API_BASE_URL + '/upload', {
            method: 'POST',
            body: formData,
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error('Upload failed');
        }

        const data = await response.json();
        if (!data.success) {
            throw new Error('Upload failed');
        }
    } catch (error) {
        console.error('Upload error:', error);
    }
}

// Mobile navigation functions
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const closeButton = document.querySelector('.sidebar-close');
    if (!sidebar || !closeButton) return;
    
    sidebar.classList.toggle('show');
    closeButton.classList.toggle('hidden');
    
    // If opening sidebar, scroll to top and ensure folders are loaded
    if (sidebar.classList.contains('show')) {
        sidebar.scrollTop = 0;
        
        // Load folders when opening sidebar
        loadFolders(true).then(folders => {
            displayFolders(folders);
        }).catch(error => {
            console.error('Error loading folders:', error);
            showNotification('Failed to load folders', 'error');
        });
    }
}

function showUploadOptions() {
    // Create and show upload modal
    const modalContent = `
        <div class="p-4">
            <input type="file" id="mobileFileInput" accept="image/png" class="hidden">
            <button class="btn w-full mb-4" onclick="document.getElementById('mobileFileInput').click()">
                Choose File
            </button>
            <div id="selectedFileName" class="text-sm mb-4"></div>
            <button class="btn btn-primary w-full" onclick="handleMobileUpload()">
                Upload
            </button>
        </div>
    `;
    showModal('Upload Screenshot', modalContent);
    
    // Handle file selection
    const fileInput = document.getElementById('mobileFileInput');
    if (!fileInput) return;
    
    fileInput.addEventListener('change', function(e) {
        const target = e.target;
        if (!(target instanceof HTMLInputElement)) return;
        const fileName = target.files?.[0]?.name || 'No file selected';
        const fileNameElement = document.getElementById('selectedFileName');
        if (fileNameElement) {
            fileNameElement.textContent = fileName;
        }
    });
}

async function handleMobileUpload() {
    const fileInput = document.getElementById('mobileFileInput');
    if (!fileInput || !(fileInput instanceof HTMLInputElement) || !fileInput.files?.length) return;
    
    const file = fileInput.files[0];
    if (typeof uploadFile === 'function') {
        await uploadFile(file, currentFolder);
        closeModal();
    }
}

function toggleMultiSelect() {
    const screenshotGrid = document.getElementById('screenshotGrid');
    if (!screenshotGrid) return;
    
    screenshotGrid.classList.toggle('multi-select-mode');
    
    // Toggle the active state of the select button
    const selectButton = document.querySelector('.mobile-controls .btn:nth-child(3)');
    if (selectButton) {
        selectButton.classList.toggle('active');
    }
    
    // Show/hide bulk actions menu
    const existingMenu = document.getElementById('bulkActionsMenu');
    if (screenshotGrid.classList.contains('multi-select-mode')) {
        if (!existingMenu) {
            const menu = document.createElement('div');
            menu.id = 'bulkActionsMenu';
            menu.innerHTML = `
                <span>0 selected</span>
                <button class="btn" onclick="moveSelectedScreenshots()">Move</button>
                <button class="btn" onclick="deleteSelectedScreenshots()">Delete</button>
                <button class="btn" onclick="toggleMultiSelect()">Cancel</button>
            `;
            document.body.appendChild(menu);
        }
    } else if (existingMenu) {
        existingMenu.remove();
    }
}

function handleMobileFolderClick(folder) {
    // Close the sidebar
    toggleSidebar();
    
    // Select the folder
    selectFolder(folder);
}

function handleScreenshotClick(event, screenshot) {
    const screenshotGrid = document.getElementById('screenshotGrid');
    if (!screenshotGrid) return;
    
    if (screenshotGrid.classList.contains('multi-select-mode')) {
        // Handle multi-select
        const item = event.target.closest('.screenshot-item');
        if (item) {
            item.classList.toggle('screenshot-selected');
            
            // Update selected count
            const selectedCount = document.querySelectorAll('.screenshot-selected').length;
            const countSpan = document.querySelector('#bulkActionsMenu span');
            if (countSpan) {
                countSpan.textContent = `${selectedCount} selected`;
            }
        }
    } else if (typeof openScreenshot === 'function') {
        // Show screenshot preview
        openScreenshot(screenshot.path);
    }
}

// Function declarations
function uploadFile(file, folder) {
    // Implementation will be provided elsewhere
    return Promise.resolve();
}

function loadScreenshots(folder) {
    // Implementation will be provided elsewhere
}

function openScreenshot(path) {
    // Implementation will be provided elsewhere
}

function showModal(title, content) {
    // Implementation will be provided elsewhere
}

function closeModal() {
    // Implementation will be provided elsewhere
}

// Mobile navigation functions
// ... rest of the code ...