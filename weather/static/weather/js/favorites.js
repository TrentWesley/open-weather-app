// FR-11 AC-3/5: save and remove favorites in place. Each favorite control holds two
// real POST forms (save / saved + remove), so without JavaScript or fetch they submit
// normally. With fetch, the form is sent with its CSRF token, the control switches
// to the other form, and the outcome is announced through the shared live region.

const FAILED = "Couldn't update your favorites. Please try again.";
const ALREADY_REMOVED = "That favorite was already removed.";
// NFR-USE-4: say what's happening if a request takes longer than 300 ms.
const BOOKMARK_SLOW_NOTICE_MS = 300;
const PROGRESS = { save: "Saving…", remove: "Removing…" };

// ---- Pure helpers (no DOM access) ----

// Which form a control should show after a response, or null to leave it as is.
function stateAfter(kind, status) {
  if (kind === "save") {
    // 409: already a favorite, so show it as saved.
    return status === 201 || status === 409 ? "saved" : null;
  }
  // 404: it is gone already (removed in another tab, for example).
  return status === 200 || status === 404 ? "unsaved" : null;
}

function messageFor(kind, status, data) {
  if (kind === "remove" && status === 404) {
    return ALREADY_REMOVED;
  }
  return (data && typeof data.message === "string" && data.message) || FAILED;
}

// Only follow same-site paths from the server ("/accounts/login/?next=...").
function isSameSitePath(url) {
  return typeof url === "string" && url.startsWith("/") && !url.startsWith("//");
}

// ---- DOM wiring ----

function announce(message) {
  const region = document.getElementById("live-region");
  if (!region) {
    return;
  }
  // Clear first so repeating the same message is announced again.
  region.textContent = "";
  window.setTimeout(() => {
    region.textContent = message;
  }, 50);
}

function showMessage(control, message, isError) {
  const element = control.querySelector("[data-favorite-message]");
  if (element) {
    element.textContent = message;
    element.classList.toggle("favorite-message-error", isError);
  }
  announce(message);
}

function showState(control, state, deleteUrl) {
  const saveForm = control.querySelector("[data-favorite-save]");
  const removeForm = control.querySelector("[data-favorite-remove]");
  if (deleteUrl && isSameSitePath(deleteUrl)) {
    removeForm.setAttribute("action", deleteUrl);
  }
  saveForm.hidden = state === "saved";
  removeForm.hidden = state !== "saved";
  // The button that was clicked is now hidden, so keep focus on the control.
  (state === "saved" ? removeForm : saveForm).querySelector("button").focus();
}

async function submitFavorite(form) {
  const control = form.closest("[data-favorite-control]");
  const kind = form.hasAttribute("data-favorite-save") ? "save" : "remove";
  const button = form.querySelector("button");
  const token = form.querySelector('input[name="csrfmiddlewaretoken"]').value;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  const slowNotice = setTimeout(() => {
    const message = control.querySelector("[data-favorite-message]");
    if (message) {
      message.textContent = PROGRESS[kind];
      message.classList.remove("favorite-message-error");
    }
  }, BOOKMARK_SLOW_NOTICE_MS);
  try {
    const response = await fetch(form.getAttribute("action"), {
      method: "POST",
      body: new FormData(form),
      headers: { Accept: "application/json", "X-CSRFToken": token },
      credentials: "same-origin",
    });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401 && isSameSitePath(data.login_url)) {
      // FR-11 AC-4: log in, then come back to this page.
      window.location.assign(data.login_url);
      return;
    }
    const state = stateAfter(kind, response.status);
    if (state) {
      showState(control, state, data.delete_url);
    }
    showMessage(control, messageFor(kind, response.status, data), !state);
  } catch (error) {
    showMessage(control, FAILED, true);
  } finally {
    clearTimeout(slowNotice);
    button.disabled = false;
    button.removeAttribute("aria-busy");
    // Disabling the focused button drops focus to the page; give it back.
    if (!form.hidden && document.activeElement === document.body) {
      button.focus();
    }
  }
}

function setUpFavorites() {
  if (!("fetch" in window) || !("FormData" in window)) {
    return; // The forms submit normally (NFR-FT-6).
  }
  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!form.matches("[data-favorite-save], [data-favorite-remove]")
        || !form.closest("[data-favorite-control]")) {
      return;
    }
    event.preventDefault();
    submitFavorite(form);
  });
}

setUpFavorites();
