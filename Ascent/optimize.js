const $ = (id) => document.getElementById(id);

const API_BASE = ""; // if same origin; otherwise set to your backend url

function setStatus(msg) {
  $("status").textContent = msg || "";
}

function showResults(show) {
  $("results").classList.toggle("hidden", !show);
}

function renderChecklist(items) {
  const ul = $("recruiterChecklist");
  ul.innerHTML = "";
  for (const t of items || []) {
    const li = document.createElement("li");
    li.textContent = t;
    ul.appendChild(li);
  }
}

function renderIssues(issues) {
  const root = $("issues");
  root.innerHTML = "";
  for (const it of issues || []) {
    const div = document.createElement("div");
    div.className = "issue";
    div.innerHTML = `
      <div class="issueTitle">${it.title || "Issue"}</div>
      <div class="issueMeta">${it.location || ""}</div>
      <div class="issueBody">
        <div><strong>Why it matters:</strong> ${it.why || ""}</div>
        <div><strong>Fix:</strong> ${it.fix || ""}</div>
        ${it.rewrite ? `<div><strong>Rewrite:</strong> ${it.rewrite}</div>` : ""}
      </div>
    `;
    root.appendChild(div);
  }
}

function renderSummaryCards(summary) {
  // keep it simple first; you can later do circular progress visuals
  $("fitCard").textContent = `Industry Fit: ${summary?.fit_score ?? "—"}`;
  $("clarityCard").textContent = `Clarity: ${summary?.clarity ?? "—"}`;
  $("keywordsCard").textContent = `Missing Keywords: ${summary?.missing_keywords_count ?? "—"}`;
}

async function optimize() {
  const file = $("resumeFile").files?.[0];
  const industry = $("industrySelect").value;

  if (!industry) {
    setStatus("Please select an industry.");
    return;
  }

  if (!file) {
    setStatus("Please attach a resume file first.");
    return;
  }

  setStatus("Uploading and optimizing...");
  showResults(false);

  const fd = new FormData();
  fd.append("resume", file);
  fd.append("industry", industry);

  const res = await fetch(`${API_BASE}/api/resume/optimize`, {
    method: "POST",
    body: fd,
  });

  if (!res.ok) {
    const text = await res.text();
    setStatus(`Failed: ${text}`);
    return;
  }

  const data = await res.json();

  setStatus("");
  showResults(true);

  renderSummaryCards(data.summary);
  renderChecklist(data.recruiter_checklist);
  $("originalText").textContent = data.original_text || "";
  $("optimizedText").textContent = data.optimized_text || "";
  renderIssues(data.issues);
}

const fileEl = $("resumeFile");
const uploadLabel = $("uploadLabel");

if (fileEl && uploadLabel) {
  fileEl.addEventListener("change", () => {
    const f = fileEl.files?.[0];
    uploadLabel.textContent = f ? f.name : "Upload";
  });
}


$("optimizeBtn").addEventListener("click", optimize);
