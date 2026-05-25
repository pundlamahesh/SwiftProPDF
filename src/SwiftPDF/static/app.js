function setStatus(statusBox, message, type) {
    if (!statusBox) {
        return;
    }

    statusBox.hidden = false;
    statusBox.textContent = message;
    statusBox.className = type === "error" ? "alert" : "status";
}

function getDownloadName(response) {
    const fallback = "download.pdf";
    const disposition = response.headers.get("Content-Disposition");
    if (!disposition) {
        return fallback;
    }

    const match = disposition.match(/filename="?([^"]+)"?/i);
    return match ? match[1] : fallback;
}

function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

async function readError(response) {
    try {
        const data = await response.json();
        return data.error || "Could not process the PDF.";
    } catch {
        return "Could not process the PDF.";
    }
}

function setupDownloadForm(form) {
    form.addEventListener("submit", async (event) => {
        event.preventDefault();

        const formCard = form.closest(".form-card");
        const statusBox = formCard ? formCard.querySelector("[data-status]") : null;
        const button = form.querySelector("button[type='submit']");
        const originalButtonText = button.textContent;
        const actionLabel = form.dataset.actionLabel || "Processing your PDF...";
        const successLabel = form.dataset.successLabel || "PDF downloaded. Form cleared.";

        button.disabled = true;
        button.textContent = "Working...";
        setStatus(statusBox, actionLabel, "status");

        try {
            const response = await fetch(form.action, {
                method: "POST",
                body: new FormData(form),
                headers: {
                    "X-Requested-With": "fetch",
                },
            });

            if (!response.ok) {
                setStatus(statusBox, await readError(response), "error");
                return;
            }

            const filename = getDownloadName(response);
            form.reset();

            const blob = await response.blob();
            downloadBlob(blob, filename);
            form.reset();
            setStatus(statusBox, successLabel, "status");
        } catch {
            setStatus(statusBox, "Something went wrong while processing the PDF.", "error");
        } finally {
            button.disabled = false;
            button.textContent = originalButtonText;
        }
    });
}

document.querySelectorAll("[data-unlock-form], [data-download-form]").forEach(setupDownloadForm);

function showTool(toolName) {
    document.querySelectorAll("[data-tool-panel]").forEach((panel) => {
        panel.hidden = panel.dataset.toolPanel !== toolName;
    });

    document.querySelectorAll("[data-tool-target]").forEach((trigger) => {
        const isActive = trigger.dataset.toolTarget === toolName;
        trigger.classList.toggle("active", isActive);
        if (isActive) {
            trigger.setAttribute("aria-current", "true");
        } else {
            trigger.removeAttribute("aria-current");
        }
    });
}

const toolsMenu = document.querySelector(".tools-menu");
const toolsMenuTrigger = toolsMenu?.querySelector(".tools-menu-trigger");

function closeToolsMenu() {
    if (!toolsMenu || !toolsMenuTrigger) {
        return;
    }

    toolsMenu.classList.remove("open");
    toolsMenuTrigger.setAttribute("aria-expanded", "false");
}

toolsMenuTrigger?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const isOpen = toolsMenu.classList.toggle("open");
    toolsMenuTrigger.setAttribute("aria-expanded", String(isOpen));
});

document.addEventListener("click", (event) => {
    if (toolsMenu && !toolsMenu.contains(event.target)) {
        closeToolsMenu();
    }
});

document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
        closeToolsMenu();
    }
});

document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-tool-target]");
    if (!trigger) {
        return;
    }

    const toolName = trigger.dataset.toolTarget;
    const panel = document.querySelector(`[data-tool-panel="${toolName}"]`);
    if (!panel) {
        return;
    }

    event.preventDefault();
    showTool(toolName);
    closeToolsMenu();
    history.replaceState(null, "", `#${toolName}`);
    panel.scrollIntoView({
        behavior: "smooth",
        block: "start",
    });
});

const initialTool = window.location.hash.replace("#", "") || "unlock";
if (document.querySelector(`[data-tool-panel="${initialTool}"]`)) {
    showTool(initialTool);
}
