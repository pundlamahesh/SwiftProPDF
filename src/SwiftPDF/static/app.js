let selectedHomepageFile = null;
const navToggle = document.querySelector('.nav-toggle');
const navMenu = document.querySelector('.nav-menu');
const themeToggle = document.querySelector('.theme-toggle');

const homePhotoSlides = [
    {
        src: '/static/home-pdf-tools.png',
        alt: 'PDF tools workspace with document pages and file controls',
        label: 'PDF Tools',
        title: 'Merge, split, rotate, and manage PDF pages.',
    },
    {
        src: '/static/home-pdf-convert.png',
        alt: 'PDF files converting into Office and image formats',
        label: 'Convert PDF',
        title: 'Turn PDFs into Word, Excel, PowerPoint, and images.',
    },
    {
        src: '/static/home-pdf-compress.png',
        alt: 'PDF compression and secure upload interface',
        label: 'Compress PDF',
        title: 'Reduce file size and export cleaner PDFs.',
    },
    {
        src: '/static/home-pdf-unlock.png',
        alt: 'Locked PDF file being unlocked in a secure interface',
        label: 'Unlock PDF',
        title: 'Open protected PDFs when you have the password.',
    },
    {
        src: '/static/home-pdf-images.png',
        alt: 'Image thumbnails being combined into a PDF document',
        label: 'Images to PDF',
        title: 'Combine scans and photos into one PDF.',
    },
    {
        src: '/static/home-pdf-edit.png',
        alt: 'PDF page thumbnails being rotated and edited',
        label: 'Edit Pages',
        title: 'Rotate pages or remove the ones you do not need.',
    },
];

function setupHomePhotoSlider() {
    const preview = document.querySelector('.upload-preview');
    if (!preview || preview.querySelector('[data-home-photo-slider]')) return;
    const dropzone = preview.querySelector('.upload-dropzone');
    if (dropzone) {
        dropzone.remove();
    }

    const slider = document.createElement('div');
    slider.className = 'home-photo-slider';
    slider.dataset.homePhotoSlider = '';
    slider.innerHTML = `
        ${homePhotoSlides.map((slide, index) => `
            <div class="home-photo-slide${index === 0 ? ' is-active' : ''}">
                <img src="${slide.src}" alt="${slide.alt}">
                <div class="home-photo-caption">
                    <span>${slide.label}</span>
                    <strong>${slide.title}</strong>
                </div>
            </div>
        `).join('')}
        <div class="home-photo-nav" aria-label="Photo slider navigation">
            <button type="button" class="home-photo-button home-photo-prev" data-photo-prev aria-label="Previous photo">‹</button>
            <button type="button" class="home-photo-button home-photo-next" data-photo-next aria-label="Next photo">›</button>
        </div>
        <div class="home-photo-dots" aria-label="PDF workflow photos">
            ${homePhotoSlides.map((slide, index) => `
                <button type="button" class="${index === 0 ? 'is-active' : ''}" aria-label="Show ${slide.label.toLowerCase()} photo"></button>
            `).join('')}
        </div>
    `;

    const body = document.createElement('div');
    body.className = 'home-preview-body';
    const stats = preview.querySelector('.hero-stats');
    if (stats) {
        preview.insertBefore(body, stats);
    } else {
        preview.appendChild(body);
    }
    body.appendChild(slider);

    const slides = [...slider.querySelectorAll('.home-photo-slide')];
    const dots = [...slider.querySelectorAll('.home-photo-dots button')];
    let activeIndex = 0;

    function showSlide(nextIndex) {
        activeIndex = nextIndex;
        slides.forEach((slide, index) => slide.classList.toggle('is-active', index === activeIndex));
        dots.forEach((dot, index) => dot.classList.toggle('is-active', index === activeIndex));
    }

    dots.forEach((dot, index) => {
        dot.addEventListener('click', () => showSlide(index));
    });

    const prevButton = slider.querySelector('[data-photo-prev]');
    const nextButton = slider.querySelector('[data-photo-next]');

    if (prevButton) {
        prevButton.addEventListener('click', () => {
            showSlide((activeIndex - 1 + slides.length) % slides.length);
        });
    }

    if (nextButton) {
        nextButton.addEventListener('click', () => {
            showSlide((activeIndex + 1) % slides.length);
        });
    }

    window.setInterval(() => {
        showSlide((activeIndex + 1) % slides.length);
    }, 4500);
}

document.addEventListener('DOMContentLoaded', setupHomePhotoSlider);

function setStatus(statusBox, message, type) {
    if (!statusBox) return;
    statusBox.hidden = false;
    statusBox.textContent = message;
    statusBox.className = type === 'error' ? 'alert' : 'status';
}

function getDownloadName(response) {
    const fallback = 'download.pdf';
    const disposition = response.headers.get('Content-Disposition');
    if (!disposition) {
        return fallback;
    }
    const match = disposition.match(/filename="?([^";]+)"?/i);
    return match ? match[1] : fallback;
}

function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

function clearFilePreviews(form) {

    form = form || document;

    form.querySelectorAll('.selected-file-name').forEach((el) => {
        el.remove();
    });

    form.querySelectorAll('.upload-selection-badge').forEach((el) => {
        el.textContent = '';
        el.classList.remove('has-file');
    });

    form.querySelectorAll('input[type="file"]').forEach((input) => {
        input.value = '';
    });

    if (typeof selectedHomepageFile !== 'undefined') {
        selectedHomepageFile = null;
    }
}

async function readError(response) {
    try {
        const payload = await response.clone().json();
        return payload?.error || 'Could not process the file.';
    } catch {
        try {
            const text = await response.text();
            const plainText = text.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
            if (plainText) {
                return plainText.slice(0, 240);
            }
        } catch {
            // Fall through to the status-based message below.
        }
        if (response.status === 413) {
            return 'The file is too large for this server.';
        }
        if (response.status >= 500) {
            return 'The server hit an error while processing this file.';
        }
        return `Could not process the file. Server returned ${response.status}.`;
    }
}

function setupDownloadForm(form) {
    const statusBox = form.querySelector('.form-status');
    const button = form.querySelector('button[type="submit"]');
    const originalLabel = button?.textContent || 'Submit';

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (!button) return;

        button.disabled = true;
        button.textContent = 'Processing...';
        setStatus(statusBox, 'Preparing your download…', 'status');

        try {
            const response = await fetch(form.action, {
                method: 'POST',
                body: new FormData(form),
                headers: {
                    'X-Requested-With': 'fetch',
                },
            });

            if (!response.ok) {
                setStatus(statusBox, await readError(response), 'error');
                return;
            }

            const filename = getDownloadName(response);
            const blob = await response.blob();
            downloadBlob(blob, filename);
            form.reset();
            clearFilePreviews(form);
            setStatus(statusBox, 'Your file is ready to download.', 'status');
        } catch (error) {
            setStatus(statusBox, 'Something went wrong while processing the file.', 'error');
             clearFilePreviews(form);
        } finally {
            button.disabled = false;
            button.textContent = originalLabel;
        }
    });
}

function bindDropzone(dropzone) {
    const fileInput = dropzone.querySelector('input[type="file"]');
    const label = dropzone.querySelector('.upload-title');
    const details = dropzone.querySelector('.upload-text');
    const selectionBadge = dropzone.querySelector('.upload-selection-badge');
    const button = dropzone.querySelector('button');

    function updateSelection(files) {
        console.log("Files selected:", files);
        const count = files.length;


        if (label) {
            label.textContent = count > 0
                ? `${count} file${count > 1 ? 's' : ''} selected`
                : 'Drop files anywhere or click to choose';
        }

        if (details) {
            details.textContent = count > 0
                ? 'Ready to process your file.'
                : 'Preview and route to the right PDF tool in seconds.';
        }

        if (selectionBadge) {
            if (count > 0) {
                const file = files[0];
                selectionBadge.textContent =
                    `📄 ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`;
            } else {
                selectionBadge.textContent = '';
            }
        }
        if (count > 0) {
    selectedHomepageFile = files[0];

    document.getElementById('quick-actions')?.removeAttribute('hidden');
    }
    }

    fileInput?.addEventListener('change', () => {
        updateSelection(fileInput.files);
    });

    const openFilePicker = () => fileInput?.click();

    button?.addEventListener('click', (event) => {
        event.preventDefault();
        openFilePicker();
    });

    dropzone.addEventListener('dragenter', (event) => {
        event.preventDefault();
        dropzone.classList.add('drag-over');
    });

    dropzone.addEventListener('dragover', (event) => {
        event.preventDefault();
        dropzone.classList.add('drag-over');
    });

    dropzone.addEventListener('dragleave', () => {
        dropzone.classList.remove('drag-over');
    });

    dropzone.addEventListener('drop', (event) => {
        event.preventDefault();
        dropzone.classList.remove('drag-over');

        const droppedFiles = event.dataTransfer?.files;

        if (droppedFiles?.length && fileInput) {
            fileInput.files = droppedFiles;
            updateSelection(droppedFiles);
        }
    });
}
    
function initNav() {
    if (!navToggle || !navMenu) return;
    navToggle.addEventListener('click', () => {
        navMenu.classList.toggle('open');
    });
    document.addEventListener('click', (event) => {
        if (!navMenu.contains(event.target) && !navToggle.contains(event.target)) {
            navMenu.classList.remove('open');
        }
    });
}

function initDropdowns() {
    const toggles = document.querySelectorAll('.dropdown-toggle');

    document.addEventListener('click', (event) => {
        const toggle = event.target.closest('.dropdown-toggle');
        if (toggle) {
            const dropdown = toggle.closest('.dropdown');
            if (!dropdown) return;
            const isOpen = toggle.getAttribute('aria-expanded') === 'true';
            const shouldOpen = !isOpen;

            document.querySelectorAll('.dropdown.open').forEach((openDropdown) => {
                if (openDropdown !== dropdown) {
                    openDropdown.classList.remove('open');
                    const openToggle = openDropdown.querySelector('.dropdown-toggle');
                    if (openToggle) {
                        openToggle.setAttribute('aria-expanded', 'false');
                    }
                }
            });

            dropdown.classList.toggle('open', shouldOpen);
            toggle.setAttribute('aria-expanded', String(shouldOpen));
            return;
        }

        if (!event.target.closest('.dropdown')) {
            document.querySelectorAll('.dropdown.open').forEach((openDropdown) => {
                openDropdown.classList.remove('open');
                const openToggle = openDropdown.querySelector('.dropdown-toggle');
                if (openToggle) {
                    openToggle.setAttribute('aria-expanded', 'false');
                }
            });
        }
    });
}

function initToolsMenu() {
    const toolsMenu = document.querySelector('.tools-menu');
    if (!toolsMenu) return;

    const trigger = toolsMenu.querySelector('.tools-menu-trigger');
    if (!trigger) return;

    trigger.addEventListener('click', (event) => {
        event.stopPropagation();
        const isOpen = trigger.getAttribute('aria-expanded') === 'true';
        toolsMenu.classList.toggle('open', !isOpen);
        trigger.setAttribute('aria-expanded', String(!isOpen));
    });

    document.addEventListener('click', (event) => {
        if (!toolsMenu.contains(event.target)) {
            toolsMenu.classList.remove('open');
            trigger.setAttribute('aria-expanded', 'false');
        }
    });
}

function initForms() {
    document.querySelectorAll('[data-download-form]').forEach(setupDownloadForm);
    document.querySelectorAll('[data-dropzone]').forEach(bindDropzone);
}

function initThemeToggle() {
    if (!themeToggle) return;
    themeToggle.addEventListener('click', () => {
        document.documentElement.classList.toggle('dark-mode');
    });
}

function initAdminSidebarToggle() {
    const sidebar = document.getElementById('admin-sidebar');
    const toggle = document.querySelector('.sidebar-toggle');
    if (!sidebar || !toggle) return;

    toggle.addEventListener('click', () => {
        const isOpen = sidebar.classList.toggle('sidebar-open');
        toggle.setAttribute('aria-expanded', String(isOpen));
    });
}

function initAdminTableSearch() {
    const searchInputs = document.querySelectorAll('[data-admin-table-search]');
    const table = document.getElementById('users-table');
    if (!table || !searchInputs.length) return;

    const rows = Array.from(table.querySelectorAll('tbody tr'));
    const storageKey = 'swiftpdf-admin-user-search';

    function applySearch(query) {
        rows.forEach((row) => {
            const text = row.textContent.toLowerCase();
            row.style.display = query && !text.includes(query) ? 'none' : '';
        });
    }

    const savedQuery = sessionStorage.getItem(storageKey) || '';
    if (savedQuery) {
        searchInputs.forEach((input) => {
            input.value = savedQuery;
        });
        applySearch(savedQuery.trim().toLowerCase());
    }

    searchInputs.forEach((input) => {
        input.addEventListener('input', () => {
            const query = input.value.trim().toLowerCase();
            sessionStorage.setItem(storageKey, input.value);
            searchInputs.forEach((peerInput) => {
                if (peerInput !== input) {
                    peerInput.value = input.value;
                }
            });
            applySearch(query);
        });
    });
}

function initAdminTableSort() {
    const table = document.getElementById('users-table');
    if (!table) return;

    const tbody = table.querySelector('tbody');
    const headers = Array.from(table.querySelectorAll('th.sortable'));
    if (!tbody || !headers.length) return;

    headers.forEach((header) => {
        header.addEventListener('click', () => {
            const index = Array.from(header.parentElement.children).indexOf(header);
            const isAscending = header.dataset.sortDirection !== 'asc';
            const sortType = header.dataset.sortType || 'text';
            const rows = Array.from(tbody.querySelectorAll('tr'));

            rows.sort((leftRow, rightRow) => {
                const leftCell = leftRow.children[index];
                const rightCell = rightRow.children[index];
                const leftValue = leftCell?.dataset.sortValue || leftCell?.textContent.trim() || '';
                const rightValue = rightCell?.dataset.sortValue || rightCell?.textContent.trim() || '';

                if (sortType === 'date') {
                    return leftValue.localeCompare(rightValue);
                }

                const leftNumber = Number(leftValue);
                const rightNumber = Number(rightValue);
                if (!Number.isNaN(leftNumber) && !Number.isNaN(rightNumber)) {
                    return leftNumber - rightNumber;
                }

                return leftValue.localeCompare(rightValue, undefined, { sensitivity: 'base' });
            });

            if (!isAscending) {
                rows.reverse();
            }

            headers.forEach((sortableHeader) => {
                sortableHeader.removeAttribute('data-sort-direction');
            });
            header.dataset.sortDirection = isAscending ? 'asc' : 'desc';
            rows.forEach((row) => tbody.appendChild(row));
        });
    });
}

function initAdminUserEditor() {
    const form = document.querySelector('[data-admin-user-form]');
    const table = document.getElementById('users-table');
    if (!form || !table) return;

    const createAction = form.dataset.createAction || form.action;
    const submitButton = form.querySelector('[data-user-submit]');
    const cancelButton = form.querySelector('[data-cancel-edit]');
    const passwordField = form.querySelector('[data-password-field]');
    const editingSummary = document.querySelector('[data-editing-summary]');
    const editingName = document.querySelector('[data-editing-name]');
    const editingEmail = document.querySelector('[data-editing-email]');
    const selectedSummary = document.querySelector('[data-selected-user-summary]');
    const selectedName = document.querySelector('[data-selected-user-name]');
    const rows = Array.from(table.querySelectorAll('[data-user-row]'));

    function field(name) {
        return form.querySelector(`[data-user-field="${name}"]`);
    }

    function clearSelection() {
        rows.forEach((row) => {
            row.classList.remove('is-selected');
            const checkbox = row.querySelector('[data-user-select]');
            if (checkbox) {
                checkbox.checked = false;
            }
        });
    }

    function resetEditor() {
        form.action = createAction;
        form.reset();
        if (passwordField) {
            passwordField.required = true;
            passwordField.placeholder = '';
        }
        if (submitButton) {
            submitButton.textContent = 'Add User';
        }
        if (cancelButton) {
            cancelButton.hidden = true;
        }
        if (editingSummary) {
            editingSummary.hidden = true;
        }
        if (selectedSummary) {
            selectedSummary.hidden = true;
        }
        clearSelection();
    }

    function selectUser(row) {
        clearSelection();
        row.classList.add('is-selected');
        const checkbox = row.querySelector('[data-user-select]');
        if (checkbox) {
            checkbox.checked = true;
        }

        form.action = row.dataset.updateAction;
        field('first_name').value = row.dataset.firstName || '';
        field('last_name').value = row.dataset.lastName || '';
        field('email').value = row.dataset.email || '';
        field('role').value = row.dataset.role || 'free';
        field('status').value = row.dataset.status || 'ACTIVE';
        field('weekly_usage').value = row.dataset.weeklyUsage || '0';
        field('premium_valid_from').value = row.dataset.premiumValidFrom || '';
        field('premium_valid_until').value = row.dataset.premiumValidUntil || '';
        field('clear_premium_validity').checked = false;

        if (passwordField) {
            passwordField.value = '';
            passwordField.required = false;
            passwordField.placeholder = 'Leave blank to keep current password';
        }
        if (submitButton) {
            submitButton.textContent = 'Save User';
        }
        if (cancelButton) {
            cancelButton.hidden = false;
        }
        if (editingName) {
            editingName.textContent = row.dataset.fullName || row.dataset.email || 'Selected user';
        }
        if (editingEmail) {
            editingEmail.textContent = row.dataset.email || '';
            editingEmail.href = `mailto:${row.dataset.email || ''}`;
        }
        if (editingSummary) {
            editingSummary.hidden = false;
        }
        if (selectedName) {
            selectedName.textContent = row.dataset.fullName || row.dataset.email || 'Selected user';
        }
        if (selectedSummary) {
            selectedSummary.hidden = false;
        }

        form.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    rows.forEach((row) => {
        row.querySelector('[data-user-select]')?.addEventListener('change', (event) => {
            if (event.target.checked) {
                selectUser(row);
            } else {
                resetEditor();
            }
        });
    });

    cancelButton?.addEventListener('click', resetEditor);
}

function initAdminDeleteConfirmation() {
    const forms = document.querySelectorAll('[data-delete-user-form]');
    const dialog = document.querySelector('[data-delete-user-dialog]');
    const nameTarget = document.querySelector('[data-delete-user-name]');
    const emailTarget = document.querySelector('[data-delete-user-email]');
    const cancelButton = document.querySelector('[data-delete-cancel]');
    const confirmButton = document.querySelector('[data-delete-confirm]');
    const feedback = document.querySelector('[data-admin-feedback]');
    let pendingForm = null;

    if (!forms.length) return;

    function showFeedback(message) {
        if (!feedback) {
            window.alert(message);
            return;
        }
        feedback.textContent = message;
        feedback.hidden = false;
        feedback.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function closeDialog() {
        pendingForm = null;
        if (dialog?.open) {
            dialog.close();
        }
    }

    forms.forEach((form) => {
        form.addEventListener('submit', (event) => {
            event.preventDefault();

            if (form.dataset.deleteBlockedMessage) {
                showFeedback(form.dataset.deleteBlockedMessage);
                return;
            }

            pendingForm = form;
            if (nameTarget) {
                nameTarget.textContent = form.dataset.userName || 'Selected user';
            }
            if (emailTarget) {
                emailTarget.textContent = form.dataset.userEmail || '';
                emailTarget.href = `mailto:${form.dataset.userEmail || ''}`;
            }

            if (dialog?.showModal) {
                dialog.showModal();
                return;
            }

            const userLabel = `${form.dataset.userName || 'Selected user'}\n${form.dataset.userEmail || ''}`;
            if (window.confirm(`Delete User\n\nAre you sure you want to delete:\n\n${userLabel}\n\nThis action cannot be undone.`)) {
                form.submit();
            }
        });
    });

    cancelButton?.addEventListener('click', closeDialog);
    dialog?.addEventListener('cancel', closeDialog);
    confirmButton?.addEventListener('click', () => {
        if (pendingForm) {
            pendingForm.submit();
        }
        closeDialog();
    });
}
function initFileInputPreviews() {
    document.querySelectorAll('input[type="file"]').forEach((input) => {
        input.addEventListener('change', () => {
            const existing = input.parentElement.querySelector('.selected-file-name');

            if (existing) {
                existing.remove();
            }

            if (input.files.length > 0) {
                const file = input.files[0];

                const preview = document.createElement('div');
                preview.className = 'selected-file-name';
               preview.innerHTML = `
    <span>
        📄 ${file.name}
        (${(file.size / 1024 / 1024).toFixed(2)} MB)
    </span>

    <button
        type="button"
        class="remove-file-btn"
        title="Remove file">
        🗑️
    </button>
`;
                input.parentElement.appendChild(preview);
                const removeBtn = preview.querySelector('.remove-file-btn');

if (removeBtn) {
    removeBtn.addEventListener('click', () => {
        input.value = '';
        preview.remove();
    });
}
            }
        });
    });
}
document.addEventListener('DOMContentLoaded', () => {
    initNav();
    initDropdowns();
    initToolsMenu();
    initForms();
    initThemeToggle();
    initAdminSidebarToggle();
    initAdminTableSearch();
    initAdminTableSort();
    initAdminUserEditor();
    initAdminDeleteConfirmation();
    initFileInputPreviews(); 
    /*initQuickActions();*/
});
