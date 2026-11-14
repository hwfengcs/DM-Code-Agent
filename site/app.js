const descriptions = {
  verified:
    "The agent runs the failing checks, reads and edits the file, then reruns the checks successfully.",
  unverified:
    "The agent changes the same file and claims completion without running the checks. The report flags the missing verification.",
};
const reportFrame = document.getElementById("report-frame");
const focusEvidence = () => {
  const doc = reportFrame.contentDocument;
  const content =
    doc?.querySelector(".notice") ||
    doc?.querySelector("section.section") ||
    doc?.querySelector("main");
  if (content) reportFrame.contentWindow.scrollTo(0, content.offsetTop);
};
reportFrame.addEventListener("load", focusEvidence);
if (reportFrame.contentDocument?.readyState === "complete") focusEvidence();
document.querySelectorAll("[data-report]").forEach((button) => {
  button.addEventListener("click", () => {
    const name = button.dataset.report;
    if (!Object.hasOwn(descriptions, name)) return;
    document
      .querySelectorAll("[data-report]")
      .forEach((item) =>
        item.setAttribute("aria-pressed", String(item === button)),
      );
    const frame = document.getElementById("report-frame");
    frame.src = `${name}.html`;
    frame.title = `${button.textContent} — interactive run report`;
    document.getElementById("open-report").href = `${name}.html`;
    document.getElementById("case-description").textContent =
      descriptions[name];
  });
});
document.getElementById("copy-command").addEventListener("click", async () => {
  const status = document.getElementById("copy-status");
  try {
    await navigator.clipboard.writeText(
      document.getElementById("install-command").textContent,
    );
    status.textContent = "Copied. Paste into your terminal.";
  } catch {
    status.textContent = "Select and copy the commands above.";
  }
});
