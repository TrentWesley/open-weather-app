// NFR-USE-4: show a loading indicator when navigation takes longer than 300 ms.
// Forms and links opt in with a data-loading attribute; without JavaScript the
// browser's own progress indicator still applies.
const LOADING_DELAY_MS = 300;

function isPlainLeftClick(event) {
  return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
}

function setUpLoadingIndicator() {
  const indicator = document.getElementById("loading-indicator");
  const liveRegion = document.getElementById("live-region");
  if (!indicator) {
    return;
  }
  let timer = null;

  function show() {
    indicator.hidden = false;
    if (liveRegion) {
      liveRegion.textContent = indicator.textContent.trim();
    }
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(show, LOADING_DELAY_MS);
  }

  function reset() {
    clearTimeout(timer);
    indicator.hidden = true;
  }

  document.addEventListener("submit", (event) => {
    if (!event.defaultPrevented && event.target.matches("form[data-loading]")) {
      schedule();
    }
  });
  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-loading]");
    if (link && !event.defaultPrevented && isPlainLeftClick(event)) {
      schedule();
    }
  });
  // Pages restored from the back/forward cache must not keep showing it.
  window.addEventListener("pageshow", reset);
}

setUpLoadingIndicator();
