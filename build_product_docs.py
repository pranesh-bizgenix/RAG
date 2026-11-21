from __future__ import annotations

import csv
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output" / "pdf"
SHOTS = OUT / "screenshots"
DIAGRAMS = OUT / "diagrams"
PDF_PATH = OUT / "BIZGENIX_Knowledge_Copilot_Complete_Product_Documentation.pdf"
DOCX_PATH = OUT / "BIZGENIX_Knowledge_Copilot_Editable_Source.docx"

WHITE = "#FFFFFF"
LIGHT = "#A8D5BA"
MINT = "#DDF2E1"
FOREST = "#397A58"
CHARCOAL = "#26332C"
GREY = "#68756D"
PALE = "#F6FAF7"
ORANGE = "#E85A2A"


SECTIONS = [
    ("Executive Summary", "sec_executive"),
    ("Product Introduction", "sec_intro"),
    ("Vision Objectives and Business Problems", "sec_vision"),
    ("Audience and Personas", "sec_personas"),
    ("Product Overview", "sec_overview"),
    ("Module and Feature Documentation", "sec_modules"),
    ("User Guides and Workflows", "sec_guides"),
    ("Architecture and Data Flow", "sec_architecture"),
    ("Roles Permissions and Access", "sec_roles"),
    ("Administration Reporting and Operations", "sec_admin"),
    ("Validation Error Handling and Troubleshooting", "sec_validation"),
    ("Security and Access Control", "sec_security"),
    ("Benefits and Operational Value", "sec_benefits"),
    ("Verified Findings and Recommendations", "sec_findings"),
    ("Frequently Asked Questions", "sec_faq"),
    ("Glossary", "sec_glossary"),
    ("Conclusion and Future Scope", "sec_conclusion"),
]


FEATURES = [
    {
        "name": "Secure sign in and session access",
        "overview": "Authenticates employees and administrators before any protected workspace is shown.",
        "purpose": "Keep the chat and administration areas behind employee credentials.",
        "problem": "Prevents anonymous access to internal knowledge and management controls.",
        "functions": "Email and password sign in; active-account check; role-aware redirect; sign out; protected routes.",
        "steps": "Open the deployment, enter assigned credentials, select Sign in, confirm the role badge, and sign out when finished.",
        "io": "Input: email and password. Output: authenticated session and role context.",
        "roles": "All active users; administrators receive the admin workspace.",
        "rules": "Valid email; password required; inactive users cannot use protected routes; employee admin requests return 403.",
        "result": "The user reaches the permitted workspace and the server associates requests with an employee record.",
        "use": "An HR employee signs in and receives the Human Resources role badge.",
        "benefit": "Users get a simple entry point; the organization gains an enforceable authentication boundary.",
        "status": "Verified",
    },
    {
        "name": "Role and department context",
        "overview": "Displays the signed-in department and applies administrator versus employee authorization.",
        "purpose": "Make access context visible and restrict management endpoints.",
        "problem": "Reduces ambiguity about which role is active and protects administrative operations.",
        "functions": "Department badge; admin-only navigation; server-side 403 enforcement for employee admin API calls.",
        "steps": "Sign in with a test role, confirm the department badge, then attempt only the functions exposed to that role.",
        "io": "Input: employee role and department. Output: role badge, navigation, and authorization decisions.",
        "roles": "Employee and administrator.",
        "rules": "Role is employee or admin; department is assigned on the employee record.",
        "result": "Employees use chat; administrators can also manage documents, people, configuration, and service health.",
        "use": "Finance and Executive accounts authenticate as employees; the Admin account reaches admin APIs.",
        "benefit": "Clarifies responsibility and reduces exposure of administrative actions.",
        "status": "Partially verified",
    },
    {
        "name": "Knowledge Copilot chat",
        "overview": "Lets employees ask free-text questions about the indexed document collection.",
        "purpose": "Turn stored documents into a conversational knowledge interface.",
        "problem": "Users otherwise search multiple files manually and may miss relevant passages.",
        "functions": "Prompt composer; Enter to send; Shift+Enter for a new line; suggested prompts; streamed responses; stop behavior.",
        "steps": "Start a new conversation, enter a question, send it, wait for the response, then refine with a follow-up.",
        "io": "Input: question up to 4,000 characters. Output: answer or retrieval-only passages plus sources.",
        "roles": "Employees and administrators.",
        "rules": "Empty messages are rejected; message length is limited; per-client rate and concurrent-generation limits apply.",
        "result": "A conversation is created, titled from the first question, and saved to history.",
        "use": "Ask what topics the knowledge base covers, then open the cited source.",
        "benefit": "Creates a faster, traceable path from question to source evidence.",
        "status": "Verified",
    },
    {
        "name": "Grounded retrieval and citations",
        "overview": "Searches indexed chunks and attaches source metadata to the response.",
        "purpose": "Make answers auditable and reduce unsupported responses.",
        "problem": "Generic chat output cannot show which internal evidence supports a claim.",
        "functions": "Vector retrieval; minimum score filtering; numbered sources; filename and page display; source-detail modal.",
        "steps": "Send a question, review Sources, select a source chip, and inspect the exact passages used.",
        "io": "Input: query and allowed document identifiers. Output: ranked passages and citation metadata.",
        "roles": "All authenticated users, limited by accessible documents when access assignments are configured.",
        "rules": "Retrieved passages are treated as reference material; weak matches are dropped; missing coverage is disclosed.",
        "result": "Users can inspect the page-level evidence behind a response.",
        "use": "Open executive_role_rag_test_content.pdf from the response source list.",
        "benefit": "Improves reviewability, training usefulness, and confidence in document-grounded answers.",
        "status": "Verified",
    },
    {
        "name": "Conversation lifecycle",
        "overview": "Maintains recent conversations and supports continued work across questions.",
        "purpose": "Preserve context and let users return to earlier research.",
        "problem": "Single-use prompts lose useful history and make follow-up questions harder.",
        "functions": "New conversation; list and reopen; automatic title; rename; delete one; delete all; clear; regenerate; copy response.",
        "steps": "Open a recent conversation, continue the thread, rename it if needed, or start a new conversation with Clear.",
        "io": "Input: messages and optional title. Output: saved thread with user and assistant messages.",
        "roles": "All authenticated users.",
        "rules": "Conversation mutations require CSRF and same-origin checks; destructive actions should be confirmed in the UI.",
        "result": "The sidebar reflects current conversation history.",
        "use": "Reopen a policy question and regenerate the latest answer after configuration changes.",
        "benefit": "Reduces repeated questions and provides continuity for research and onboarding.",
        "status": "Verified",
    },
    {
        "name": "Document ingestion and access assignment",
        "overview": "Lets administrators upload supported files, validate them, assign access, and index their content.",
        "purpose": "Keep the knowledge base current and controllable.",
        "problem": "A RAG system needs governed ingestion rather than unmanaged file copying.",
        "functions": "Multi-file upload; type and signature validation; duplicate detection; department and employee assignment; status tracking.",
        "steps": "Open Documents, select files, choose access, upload, monitor status, and verify indexed chunks before use.",
        "io": "Input: supported file and access metadata. Output: stored document record, parsed chunks, and index entries.",
        "roles": "Administrator only.",
        "rules": "Allow-listed extensions; size and count limits; server-generated storage names; duplicate hash checks.",
        "result": "Successfully indexed documents become available to retrieval according to access metadata.",
        "use": "Upload an HR policy PDF and assign it to Human Resources.",
        "benefit": "Provides a repeatable governance path for adding internal knowledge.",
        "status": "Verified from deployed API and source",
    },
    {
        "name": "Document management and preview",
        "overview": "Provides search, filters, details, logs, previews, downloads, access edits, reindexing, delete, and short undo.",
        "purpose": "Give administrators operational control over knowledge assets.",
        "problem": "Without visibility, failed parsing and stale access assignments are hard to correct.",
        "functions": "List and filter; details; chunk preview; original-file view; access update; reindex; delete and restore window.",
        "steps": "Find a document, open details, inspect status and preview, update access or reindex, and verify the result.",
        "io": "Input: document identifier and management action. Output: updated metadata, events, and vector state.",
        "roles": "Administrator only.",
        "rules": "State-changing actions require CSRF; unsafe file rendering is constrained by response headers.",
        "result": "The document record and its index state remain synchronized.",
        "use": "Reindex a file after embedding configuration changes.",
        "benefit": "Shortens diagnosis and reduces the risk of stale or unintended content.",
        "status": "Verified from deployed API and source",
    },
    {
        "name": "Employee and department administration",
        "overview": "Manages employee identity, department, role, status, and password updates.",
        "purpose": "Maintain the people and organization model used by authentication and document access.",
        "problem": "Role-aware retrieval requires reliable employee and department records.",
        "functions": "List and filter employees; create and edit; activate or suspend; delete; create and delete departments.",
        "steps": "Create a department, add an employee, assign role and status, then test sign in and document access.",
        "io": "Input: employee ID, name, email, department, role, status, and password. Output: validated employee record.",
        "roles": "Administrator only.",
        "rules": "Unique ID and email; valid email; password 8-256 characters; at least one active administrator; no self-deletion.",
        "result": "The employee can authenticate when active and receives the assigned context.",
        "use": "Suspend a departing employee without deleting audit history.",
        "benefit": "Centralizes access administration and reduces accidental lockout.",
        "status": "Verified from deployed API and source",
    },
    {
        "name": "Knowledge base operations and health",
        "overview": "Shows index size, ingestion activity, events, configuration, dependencies, and service checks.",
        "purpose": "Help administrators determine whether retrieval is ready and healthy.",
        "problem": "Silent ingestion or dependency failures can produce empty or misleading chat results.",
        "functions": "Overview metrics; event log; service health; reindex one or all; retrieval settings; uptime and environment.",
        "steps": "Review health, investigate failed checks, inspect events, correct the dependency, and reindex if required.",
        "io": "Input: administrative request. Output: status checks, index metadata, and operational events.",
        "roles": "Administrator only.",
        "rules": "Health reflects database, worker, storage, persistence, LLM, embeddings, and OCR availability.",
        "result": "Administrators can distinguish a content issue from a service or configuration issue.",
        "use": "Identify that the LLM is not configured and OCR is unavailable on the deployment.",
        "benefit": "Reduces troubleshooting time and improves operational transparency.",
        "status": "Verified",
    },
    {
        "name": "Language model configuration",
        "overview": "Supports administrator selection of a model provider, model, base URL, and API key.",
        "purpose": "Enable generated answers while retaining retrieval-only fallback.",
        "problem": "Deployments need flexible provider choice and a safe degraded mode.",
        "functions": "Provider catalog; configuration status; API key write-only behavior; runtime activation; retrieval-only mode.",
        "steps": "Open Settings, select a provider and model, enter the key, save, then test a new conversation.",
        "io": "Input: provider settings and credential. Output: active client configuration without returning the stored key.",
        "roles": "Administrator only.",
        "rules": "Configuration is validated; saved keys are never returned to the browser; runtime files on Vercel are instance-local.",
        "result": "New questions use the configured provider or fall back to retrieved passages when disabled.",
        "use": "Enable a supported provider after deployment and validate a cited generated answer.",
        "benefit": "Allows provider choice while maintaining basic knowledge access during outages or incomplete setup.",
        "status": "Verified; currently disabled",
    },
]


FINDINGS = [
    ("High", "Departmental isolation is not configured", "All four indexed documents are assigned to all departments. HR, Finance, and Executive accounts receive the same prompt suggestions and cross-department retrieval passages.", "Assign each document to its intended department or named employees, then run a role-by-role regression test before claiming departmental isolation."),
    ("High", "Language model is not configured", "The deployment returns retrieval-only passages and explicitly reports that no LLM provider is configured.", "Configure a production-approved provider and test answer quality, timeout behavior, and source fidelity."),
    ("High", "Runtime uploads are not durable on Vercel", "The health endpoint reports durable Turso records but temporary uploaded originals and runtime vector-index changes.", "Move documents and vector state to durable object and vector storage before relying on admin uploads in production."),
    ("Medium", "Image OCR is unavailable", "The health check reports that Tesseract is not on PATH and image uploads will fail.", "Install OCR in a supported runtime or disable image upload claims and provide a clear validation message."),
    ("Medium", "Shared conversation workspace behavior requires product confirmation", "The source implementation lists conversations through a shared workspace identifier; role accounts showed a common history count and titles.", "Decide whether history should be per user, per department, or shared; enforce ownership accordingly and document the privacy model."),
    ("Medium", "Document access defaults need safer governance", "The current corpus uses an all-departments assignment, which defeats the stated role-based access objective.", "Default new restricted business documents to no access until an administrator explicitly assigns scope."),
    ("Low", "Deployment readiness messaging can be clearer", "The UI shows RAG and sources, but operational limitations are visible mainly in the admin health area.", "Expose an administrator readiness checklist for LLM, persistence, OCR, access assignments, and retrieval regression tests."),
]


ROLE_ROWS = [
    ("Human Resources employee", "Chat, history, sources, theme, about", "No admin APIs", "Badge verified; current documents are not department-isolated"),
    ("Finance employee", "Chat, history, sources, theme, about", "No admin APIs", "Authenticated; same suggestions and retrieval scope as HR"),
    ("Executive employee", "Chat, history, sources, theme, about", "No admin APIs", "Authenticated; same suggestions and retrieval scope as HR"),
    ("Administrator", "All chat functions plus administration", "Documents, employees, departments, health, events, model settings", "Admin API access verified"),
]


def ensure_outputs() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    DIAGRAMS.mkdir(parents=True, exist_ok=True)


def write_supporting_files() -> None:
    ensure_outputs()
    with (OUT / "feature_inventory_checklist.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Feature", "Status", "Primary roles", "Evidence"])
        for item in FEATURES:
            writer.writerow([item["name"], item["status"], item["roles"], item["result"]])
    unverified = """# Inaccessible and unverified functionality

Assessment date: 21 November 2026

- No separate manager or business-owner account was supplied; their experience is described as a stakeholder perspective, not a verified UI role.
- Generated-answer quality could not be verified because the deployed language model is disabled.
- Production-scale performance, concurrency, uptime, disaster recovery, and backup restoration were not load-tested.
- Email, SMS, Slack, Teams, and other outbound notification integrations were not present or verified. A WhatsApp integration is not part of this RAG deployment.
- Durable object storage and a shared vector database are not connected in the assessed Vercel deployment.
- Image OCR could not be exercised because the health check reports Tesseract unavailable.
- Mobile and tablet visual behavior was not fully tested.
- Accessibility was inspected through semantic control labels but not audited against WCAG with assistive-technology test cases.
- File preview behavior was not exercised for every supported extension.
- Delete, restore, suspend, password-change, reindex-all, and live provider-save actions were documented from verified routes and validations but were not executed against the shared deployment to avoid changing other users' data.
- Departmental retrieval isolation cannot be verified while every indexed document is assigned to all departments.
"""
    (OUT / "inaccessible_and_unverified.md").write_text(unverified, encoding="utf-8")
    architecture = """flowchart LR
  U[Authenticated employee] --> B[Browser workspace]
  A[Administrator] --> B
  B --> V[Vercel Python application]
  V --> AUTH[Session and role checks]
  V --> CHAT[Conversation service]
  V --> DOC[Document service]
  AUTH --> DB[(Turso database)]
  CHAT --> RET[Retriever]
  DOC --> PARSE[Parsers and chunking]
  PARSE --> IDX[(Vector index)]
  RET --> IDX
  RET --> LLM[Optional LLM provider]
  LLM --> B
  RET --> B
"""
    rag_flow = """flowchart TD
  Q[User question] --> S[Validate and save message]
  S --> P[Resolve accessible document IDs]
  P --> R[Retrieve ranked chunks]
  R --> C[Attach source metadata]
  C --> M{LLM configured?}
  M -- Yes --> G[Generate grounded answer]
  M -- No --> F[Return retrieval-only passages]
  G --> O[Stream answer and sources]
  F --> O
  O --> H[Save response in conversation history]
"""
    access_flow = """flowchart TD
  L[Sign in] --> I{Account active?}
  I -- No --> D[Deny access]
  I -- Yes --> R{Role}
  R -- Employee --> C[Chat workspace]
  R -- Administrator --> C
  R -- Administrator --> A[Admin workspace]
  C --> P[Filter retrieval by document access assignments]
  P --> N[Current deployment: all documents assigned to all]
"""
    (DIAGRAMS / "system_architecture.mmd").write_text(architecture, encoding="utf-8")
    (DIAGRAMS / "rag_answer_flow.mmd").write_text(rag_flow, encoding="utf-8")
    (DIAGRAMS / "role_access_flow.mmd").write_text(access_flow, encoding="utf-8")


def build_pdf() -> None:
    from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Image, PageBreak,
        Table, TableStyle, KeepTogether, NextPageTemplate, CondPageBreak,
    )
    from reportlab.platypus.tableofcontents import TableOfContents
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase import pdfmetrics

    ensure_outputs()
    page_w, page_h = A4
    font = "Helvetica"
    bold = "Helvetica-Bold"
    for path, name in [
        (Path("C:/Windows/Fonts/aptos.ttf"), "Aptos"),
        (Path("C:/Windows/Fonts/aptos-bold.ttf"), "Aptos-Bold"),
    ]:
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont(name, str(path)))
                if "Bold" in name:
                    bold = name
                else:
                    font = name
            except Exception:
                pass

    class HandbookDoc(BaseDocTemplate):
        def __init__(self, filename: str):
            super().__init__(filename, pagesize=A4, leftMargin=18*mm, rightMargin=18*mm,
                             topMargin=22*mm, bottomMargin=18*mm, title="BIZGENIX Knowledge Copilot Complete Product Documentation",
                             author="BIZGENIX AI")
            cover = Frame(0, 0, page_w, page_h, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="cover")
            body = Frame(self.leftMargin, self.bottomMargin, page_w-self.leftMargin-self.rightMargin,
                         page_h-self.topMargin-self.bottomMargin, id="body")
            self.addPageTemplates([
                PageTemplate(id="Cover", frames=[cover], onPage=self.cover_page),
                PageTemplate(id="Body", frames=[body], onPage=self.body_page),
            ])
            self.heading_no = 0

        def cover_page(self, canvas, doc):
            canvas.saveState()
            canvas.setFillColor(colors.HexColor(WHITE)); canvas.rect(0, 0, page_w, page_h, fill=1, stroke=0)
            canvas.setFillColor(colors.HexColor(MINT)); canvas.roundRect(12*mm, 12*mm, page_w-24*mm, page_h-24*mm, 8*mm, fill=1, stroke=0)
            canvas.setFillColor(colors.HexColor(WHITE)); canvas.roundRect(21*mm, 21*mm, page_w-42*mm, page_h-42*mm, 6*mm, fill=1, stroke=0)
            canvas.setFillColor(colors.HexColor(LIGHT)); canvas.circle(page_w-31*mm, page_h-31*mm, 18*mm, fill=1, stroke=0)
            canvas.setFillColor(colors.HexColor(FOREST)); canvas.circle(page_w-31*mm, page_h-31*mm, 8*mm, fill=1, stroke=0)
            logo = ROOT / "public" / "static" / "img" / "bizgenix-logo.png"
            if logo.exists():
                canvas.drawImage(str(logo), 31*mm, page_h-55*mm, width=55*mm, height=17*mm, preserveAspectRatio=True, mask="auto")
            canvas.setFillColor(colors.HexColor(CHARCOAL)); canvas.setFont(bold, 28)
            canvas.drawString(31*mm, page_h-95*mm, "Knowledge Copilot")
            canvas.setFont(bold, 18); canvas.setFillColor(colors.HexColor(FOREST))
            canvas.drawString(31*mm, page_h-108*mm, "Complete Product Documentation")
            canvas.setFont(font, 11); canvas.setFillColor(colors.HexColor(GREY))
            canvas.drawString(31*mm, page_h-124*mm, "Role-based AI RAG system")
            canvas.drawString(31*mm, page_h-132*mm, "Deployment assessed 21 November 2026")
            canvas.setFillColor(colors.HexColor(CHARCOAL)); canvas.setFont(font, 10)
            canvas.drawString(31*mm, 42*mm, "Prepared for client onboarding, product demonstrations, training, and stakeholder review")
            canvas.setFillColor(colors.HexColor(FOREST)); canvas.setFont(bold, 10)
            canvas.drawString(31*mm, 32*mm, "DOCUMENT VERSION 1.0")
            canvas.restoreState()

        def body_page(self, canvas, doc):
            canvas.saveState()
            if doc.page > 1:
                canvas.setStrokeColor(colors.HexColor(LIGHT)); canvas.setLineWidth(0.7)
                canvas.line(18*mm, page_h-15*mm, page_w-18*mm, page_h-15*mm)
                canvas.setFillColor(colors.HexColor(FOREST)); canvas.setFont(bold, 8.5)
                canvas.drawString(18*mm, page_h-11*mm, "BIZGENIX AI")
                canvas.setFillColor(colors.HexColor(GREY)); canvas.setFont(font, 8)
                canvas.drawRightString(page_w-18*mm, page_h-11*mm, "Knowledge Copilot Product Documentation")
                canvas.setStrokeColor(colors.HexColor(MINT)); canvas.line(18*mm, 13*mm, page_w-18*mm, 13*mm)
                canvas.setFillColor(colors.HexColor(GREY)); canvas.drawString(18*mm, 8.5*mm, "Verified deployment handbook")
                canvas.drawRightString(page_w-18*mm, 8.5*mm, f"Page {doc.page}")
            canvas.restoreState()

        def afterFlowable(self, flowable):
            if isinstance(flowable, Paragraph) and flowable.style.name in ("H1", "H2"):
                level = 0 if flowable.style.name == "H1" else 1
                text = flowable.getPlainText()
                key = getattr(flowable, "_bookmarkName", f"h{self.seq.nextf('heading')}")
                self.canv.bookmarkPage(key)
                if level == 0:
                    self.canv.addOutlineEntry(text, key, level=0, closed=False)
                self.notify("TOCEntry", (level, text, self.page, key))

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="H1", fontName=bold, fontSize=19, leading=23, textColor=colors.HexColor(CHARCOAL),
                              spaceBefore=7*mm, spaceAfter=4*mm, keepWithNext=True))
    styles.add(ParagraphStyle(name="H2", fontName=bold, fontSize=13, leading=16, textColor=colors.HexColor(FOREST),
                              spaceBefore=4.5*mm, spaceAfter=2*mm, keepWithNext=True))
    styles.add(ParagraphStyle(name="H3", fontName=bold, fontSize=10.5, leading=13, textColor=colors.HexColor(CHARCOAL),
                              spaceBefore=3*mm, spaceAfter=1.2*mm, keepWithNext=True))
    styles.add(ParagraphStyle(name="Body", fontName=font, fontSize=9.2, leading=13.2, textColor=colors.HexColor(CHARCOAL),
                              spaceAfter=2.2*mm))
    styles.add(ParagraphStyle(name="Small", fontName=font, fontSize=7.8, leading=10.5, textColor=colors.HexColor(GREY),
                              spaceAfter=1.4*mm))
    styles.add(ParagraphStyle(name="Caption", fontName=font, fontSize=7.6, leading=10, textColor=colors.HexColor(GREY),
                              alignment=TA_CENTER, spaceBefore=1.2*mm, spaceAfter=3*mm))
    styles.add(ParagraphStyle(name="Bullet2", fontName=font, fontSize=8.8, leading=12.5, leftIndent=5*mm,
                              firstLineIndent=-3*mm, bulletIndent=1*mm, textColor=colors.HexColor(CHARCOAL), spaceAfter=1.2*mm))
    styles.add(ParagraphStyle(name="Metric", fontName=bold, fontSize=17, leading=19, textColor=colors.HexColor(FOREST), alignment=TA_CENTER))

    def h1(text, key):
        p = Paragraph(f'<a name="{key}"/>{text}', styles["H1"]); p._bookmarkName = key; return p
    def h2(text): return Paragraph(text, styles["H2"])
    def h3(text): return Paragraph(text, styles["H3"])
    def body(text): return Paragraph(text, styles["Body"])
    def bullet(text): return Paragraph(text, styles["Bullet2"], bulletText="-")

    def table(data, widths, header=True, font_size=7.6):
        cells = [[Paragraph(str(c), styles["Small"]) for c in row] for row in data]
        t = Table(cells, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
        commands = [
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#D9D9D9")),
            ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5),
            ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ]
        if header:
            commands += [("BACKGROUND", (0,0), (-1,0), colors.HexColor(FOREST)), ("TEXTCOLOR", (0,0), (-1,0), colors.white)]
            for c in cells[0]:
                for r in c.frags: r.textColor = colors.white; r.fontName = bold
        for i in range(1 if header else 0, len(data)):
            if i % 2 == 0: commands.append(("BACKGROUND", (0,i), (-1,i), colors.HexColor(PALE)))
        t.setStyle(TableStyle(commands)); return t

    def screenshot(filename, caption):
        path = SHOTS / filename
        if not path.exists(): return []
        img = Image(str(path), width=171*mm, height=106*mm, kind="proportional")
        img.hAlign = "CENTER"
        box = Table([[img]], colWidths=[173*mm], style=TableStyle([
            ("BOX", (0,0), (-1,-1), 0.6, colors.HexColor(LIGHT)), ("BACKGROUND", (0,0), (-1,-1), colors.white),
            ("LEFTPADDING", (0,0), (-1,-1), 3), ("RIGHTPADDING", (0,0), (-1,-1), 3),
            ("TOPPADDING", (0,0), (-1,-1), 3), ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ]))
        return [box, Paragraph(caption, styles["Caption"])]

    def feature_block(item):
        rows = [
            ["Feature overview", item["overview"]], ["Purpose", item["purpose"]], ["Business problem", item["problem"]],
            ["Key functionality", item["functions"]], ["How to use", item["steps"]], ["Inputs and outputs", item["io"]],
            ["Roles", item["roles"]], ["Rules and validations", item["rules"]], ["Expected result", item["result"]],
            ["Practical use case", item["use"]], ["User and organization benefit", item["benefit"]], ["Verification", item["status"]],
        ]
        data = [[Paragraph(f"<b>{a}</b>", styles["Small"]), Paragraph(b, styles["Small"])] for a,b in rows]
        t = Table(data, colWidths=[40*mm, 131*mm], hAlign="LEFT")
        t.setStyle(TableStyle([
            ("VALIGN", (0,0), (-1,-1), "TOP"), ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#D9D9D9")),
            ("BACKGROUND", (0,0), (0,-1), colors.HexColor(MINT)), ("TEXTCOLOR", (0,0), (0,-1), colors.HexColor(FOREST)),
            ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5),
            ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ]))
        return [h2(item["name"]), t, Spacer(1, 2.5*mm)]

    def diagram_box(title, nodes, arrows):
        import math
        d = Drawing(480, 210)
        d.add(Rect(0,0,480,210,rx=12,ry=12,fillColor=colors.HexColor(PALE),strokeColor=colors.HexColor(LIGHT)))
        positions = {}
        for label,x,y,w in nodes:
            positions[label]=(x,y,w)
            d.add(Rect(x,y,w,34,rx=8,ry=8,fillColor=colors.white,strokeColor=colors.HexColor(FOREST),strokeWidth=1.2))
            d.add(String(x+w/2,y+13,label,fontName=font,fontSize=8,textAnchor="middle",fillColor=colors.HexColor(CHARCOAL)))
        for a,b in arrows:
            ax,ay,aw=positions[a]; bx,by,bw=positions[b]
            acx,acy=ax+aw/2,ay+17; bcx,bcy=bx+bw/2,by+17
            dx,dy=bcx-acx,bcy-acy
            if abs(dx) >= abs(dy):
                x1=ax+aw if dx >= 0 else ax; y1=acy
                x2=bx if dx >= 0 else bx+bw; y2=bcy
            else:
                x1=acx; y1=ay+34 if dy >= 0 else ay
                x2=bcx; y2=by if dy >= 0 else by+34
            d.add(Line(x1,y1,x2,y2,strokeColor=colors.HexColor(FOREST),strokeWidth=1))
            angle=math.atan2(y2-y1,x2-x1); size=5; wing=3
            p1=(x2-size*math.cos(angle)+wing*math.sin(angle),y2-size*math.sin(angle)-wing*math.cos(angle))
            p2=(x2-size*math.cos(angle)-wing*math.sin(angle),y2-size*math.sin(angle)+wing*math.cos(angle))
            d.add(Polygon([x2,y2,p1[0],p1[1],p2[0],p2[1]],fillColor=colors.HexColor(FOREST),strokeColor=None))
        d.add(String(16,190,title,fontName=bold,fontSize=11,fillColor=colors.HexColor(FOREST)))
        return d

    story = []
    # The first page uses the Cover template by default. Select Body before the
    # page break so the document-control page cannot inherit cover artwork.
    story += [NextPageTemplate("Body"), Spacer(1, page_h-2*mm), PageBreak()]
    story += [h1("Document Control", "sec_control")]
    story += [table([
        ["Field", "Value"], ["Document", "BIZGENIX Knowledge Copilot Complete Product Documentation"],
        ["Version", "1.0"], ["Assessment date", "21 November 2026"], ["Application", "https://rag-two-ivory.vercel.app/"],
        ["Company", "BIZGENIX AI"], ["Classification", "Product and deployment documentation"],
        ["Evidence basis", "Deployed UI, authenticated APIs, application source, and health checks"],
    ], [42*mm,129*mm]), Spacer(1,5*mm)]
    story += [h2("Scope and evidence status"), body("This handbook describes the deployed role-based RAG application, its end-user experience, administrative capabilities, verified workflows, operating model, benefits, and current deployment limitations. Claims marked verified were observed in the deployed application or confirmed through authenticated APIs and matching source. Suggested future work is separated from shipped behavior."),
              body('Deployment link: <link href="https://rag-two-ivory.vercel.app/" color="#397A58">rag-two-ivory.vercel.app</link>')]
    story += [PageBreak(), h1("Table of Contents", "sec_toc")]
    toc = TableOfContents(); toc.levelStyles = [
        ParagraphStyle(name="TOC1", fontName=bold, fontSize=10.2, leading=15, leftIndent=0, firstLineIndent=0, textColor=colors.HexColor(CHARCOAL), spaceBefore=2),
        ParagraphStyle(name="TOC2", fontName=font, fontSize=8.5, leading=12, leftIndent=10*mm, firstLineIndent=0, textColor=colors.HexColor(GREY)),
    ]
    story += [toc, PageBreak()]

    story += [h1("Executive Summary", "sec_executive"),
              body("BIZGENIX Knowledge Copilot is an authenticated document question-answering product with employee and administrator roles. Employees ask questions, retain conversation history, and inspect source passages. Administrators manage documents, access assignments, employees, departments, indexing, language-model configuration, events, and service health."),
              body("The assessed deployment is operational in retrieval-only mode. Authentication and administrator authorization work, four documents are indexed into 28 chunks, and employee admin API requests are rejected. The most important readiness gap is that every document is assigned to all departments, so the current deployment does not demonstrate departmental knowledge isolation. The second major gap is the absence of a configured language model, which limits responses to retrieved passages."),
              body('See <link href="#sec_findings" color="#397A58">Verified Findings and Recommendations</link> for the prioritized remediation plan.')]
    metric_data = [[Paragraph("4",styles["Metric"]),Paragraph("28",styles["Metric"]),Paragraph("4",styles["Metric"]),Paragraph("0",styles["Metric"])],
                   [Paragraph("indexed documents",styles["Small"]),Paragraph("indexed chunks",styles["Small"]),Paragraph("active test accounts",styles["Small"]),Paragraph("configured LLMs",styles["Small"])]]
    mt=Table(metric_data,colWidths=[42.5*mm]*4); mt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor(MINT)),("BOX",(0,0),(-1,-1),0.5,colors.HexColor(LIGHT)),("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor(WHITE)),("ALIGN",(0,0),(-1,-1),"CENTER"),("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8)])); story += [Spacer(1,3*mm),mt]

    story += [h1("Product Introduction", "sec_intro"),
              body("The product provides a branded internal knowledge workspace. It combines protected employee access, a conversational interface, document retrieval, source inspection, persistent conversation history, and an administrator control plane. Its core value is not a generic chatbot; it is the connection between a business question and the exact indexed passages used to answer it."),
              h2("Product vision"), body("Give the right employee a fast, understandable, and traceable way to use company knowledge while administrators retain control over people, documents, access scope, indexing, and model configuration."),
              h2("Verified product objectives"), bullet("Require authentication before protected application access."), bullet("Expose employee role and department context in the workspace."), bullet("Retrieve relevant document passages and attach source metadata."), bullet("Preserve conversations for follow-up work."), bullet("Provide administrators with governed ingestion and operational visibility."), bullet("Degrade to retrieval-only output when no language model is configured.")]

    story += [h1("Vision Objectives and Business Problems", "sec_vision"),
              table([["Problem", "Product response", "Business effect"],
                     ["Knowledge is spread across files", "Conversational retrieval across indexed chunks", "Less manual browsing and clearer evidence"],
                     ["Answers can be hard to verify", "Source chips with filenames, pages, and passages", "Faster review and correction"],
                     ["Sensitive knowledge needs governance", "Authentication, roles, departments, and document access assignments", "A basis for controlled distribution"],
                     ["Content changes over time", "Upload, status, reindex, events, and access editing", "Operational control over the corpus"],
                     ["AI services may be unavailable", "Retrieval-only fallback", "Basic knowledge lookup remains available"],
                     ["Administrators need readiness signals", "Health checks and index metrics", "Quicker diagnosis of configuration and dependency gaps"]], [43*mm,66*mm,62*mm])]

    story += [h1("Audience and Personas", "sec_personas"),
              table([["Persona", "Primary need", "Typical tasks", "Success signal"],
                     ["Department employee", "Answers within permitted business knowledge", "Ask, follow up, inspect sources, reopen history", "Relevant evidence without admin exposure"],
                     ["Administrator", "Governed and healthy knowledge service", "Manage documents, access, users, settings, and health", "Indexed content and controlled access"],
                     ["Manager", "Consistent team use and trusted references", "Review responses and coach workflows", "Fewer ambiguous policy answers"],
                     ["Business owner", "Operational visibility and adoption", "Review readiness, risks, and value", "Known limitations and clear ownership"]], [35*mm,48*mm,55*mm,33*mm]),
              body("Manager and business-owner perspectives are stakeholder personas, not separately verified application roles in this assessment.")]

    story += [h1("Product Overview", "sec_overview")]
    story += screenshot("01_login.png", "Figure 1. Protected BIZGENIX sign-in. Credentials are never shown in the documentation screenshots.")
    story += [h2("User experience map"), table([["Area", "Purpose", "Verified elements"],
        ["Sign in", "Authenticate employees and administrators", "Email, password, secure-workspace message"],
        ["Chat workspace", "Ask and refine knowledge questions", "Role badge, RAG indicator, suggestions, composer"],
        ["Conversation sidebar", "Return to earlier research", "New, recent, rename, delete, delete all, sign out"],
        ["Answer view", "Review grounded output", "Retrieved passages, source list, copy, regenerate"],
        ["Source detail", "Inspect evidence", "Filename, page list, exact passage excerpts"],
        ["Admin workspace", "Operate the service", "Documents, people, departments, settings, events, health"]], [36*mm,55*mm,80*mm])]
    story += screenshot("02_hr_workspace.png", "Figure 2. HR employee workspace with role context, suggestions, recent conversations, and message composer.")

    story += [PageBreak(), h1("Module and Feature Documentation", "sec_modules"),
              body("Each feature below uses a consistent product-documentation pattern and distinguishes verified behavior from current configuration or source-confirmed capability.")]
    for i,item in enumerate(FEATURES):
        story += feature_block(item)
        if i in (2,5,8): story += [PageBreak()]
    story += screenshot("03_hr_retrieval_response.png", "Figure 3. Retrieval-only response with visible sources. The HR session received Executive and Finance material because the documents are currently assigned to all departments.")
    story += screenshot("04_about_rag.png", "Figure 4. In-product explanation of retrieval-augmented generation and source inspection.")
    story += screenshot("05_source_detail.png", "Figure 5. Source-detail modal showing the exact pages and passages used by retrieval.")

    story += [h1("User Guides and Workflows", "sec_guides"), h2("Employee quick start")]
    for n,t in enumerate(["Open the deployment and sign in with an active employee account.","Confirm the department badge before asking a sensitive question.","Select a suggested prompt or write a focused question in the message box.","Review the retrieved answer and the Sources section.","Open each important source chip and read the exact passage.","Ask a follow-up, copy the response, regenerate it, or return later from Recent.","Sign out when using a shared device."],1): story += [body(f"<b>{n}.</b> {t}")]
    story += [h2("Administrator document onboarding")]
    for n,t in enumerate(["Confirm the target department or named employees before upload.","Open Documents and select only supported, non-confidential test files for validation.","Set department or employee access explicitly. Avoid the all-departments scope for restricted material.","Upload and monitor queued, processing, indexed, or failed status.","Open details, preview chunks, and confirm the expected document content.","Run a role-by-role retrieval test with positive and negative access cases.","Record the result and correct access metadata before production use."],1): story += [body(f"<b>{n}.</b> {t}")]
    story += [h2("End-to-end answer workflow"), diagram_box("RAG answer flow",[("Question",20,135,75),("Access scope",135,135,90),("Retrieve",270,135,75),("Sources",385,135,75),("LLM or fallback",135,55,105),("Stream answer",300,55,105)],[("Question","Access scope"),("Access scope","Retrieve"),("Retrieve","Sources"),("Access scope","LLM or fallback"),("LLM or fallback","Stream answer"),("Sources","Stream answer")]), Paragraph("Figure 6. A question is validated, scoped to accessible documents, retrieved, cited, generated or returned in fallback mode, then streamed and saved.",styles["Caption"])]

    story += [h1("Architecture and Data Flow", "sec_architecture"),
              body("The architecture below is based on the deployed health responses and matching application source. It describes the current Vercel adaptation without inventing unobserved infrastructure."),
              diagram_box("Verified system architecture",[("Browser",20,135,75),("Vercel app",135,135,90),("Auth",275,155,70),("Chat",275,110,70),("Admin",275,65,70),("Turso DB",390,155,70),("Vector index",390,100,70),("LLM optional",390,45,70)],[("Browser","Vercel app"),("Vercel app","Auth"),("Vercel app","Chat"),("Vercel app","Admin"),("Auth","Turso DB"),("Chat","Vector index"),("Chat","LLM optional")]),
              Paragraph("Figure 7. Browser requests reach the Vercel Python application, which coordinates authentication, conversations, document administration, retrieval, and an optional LLM provider.",styles["Caption"]),
              h2("Persistence model"),
              body("Turso durably stores employee, department, session, permission, conversation, and document metadata in the assessed deployment. Vercel function file storage remains instance-local. The health service explicitly reports that uploaded originals and runtime vector-index changes are temporary."),
              h2("Document ingestion flow"),
              body("Upload requests are validated, deduplicated with SHA-256, stored under server-generated names, parsed into chunks, embedded, and atomically swapped into the vector index. A document becomes searchable only after indexing completes. Failed processing records an error for administrators.")]

    story += [h1("Roles Permissions and Access", "sec_roles"), table([["Role", "Employee functions", "Administrative functions", "Assessment note"],*ROLE_ROWS],[39*mm,48*mm,43*mm,41*mm]),
              h2("Observed access behavior"),
              body("All employee accounts returned HTTP 403 for the administrator bootstrap endpoint. The administrator returned HTTP 200 and could read document, employee, department, health, and configuration data. This verifies the employee-versus-administrator boundary."),
              h2("Current departmental access gap"),
              body("All indexed documents have department scope set to all. Consequently, each department receives the same suggested prompts and retrieval passages. The access-control mechanism exists, but departmental isolation is not configured in the current corpus. This must be corrected before the deployment is represented as department-restricted."),
              h2("Recommended acceptance test"),
              table([["Test", "HR", "Finance", "Executive", "Expected"],
                     ["Retrieve HR-only document", "Allow", "Deny", "Deny", "Only HR source returned"],
                     ["Retrieve Finance-only document", "Deny", "Allow", "Deny", "Only Finance source returned"],
                     ["Retrieve Executive-only document", "Deny", "Deny", "Allow", "Only Executive source returned"],
                     ["Open admin API", "Deny", "Deny", "Deny", "HTTP 403"],
                     ["Admin manages access", "N/A", "N/A", "N/A", "Administrator succeeds"]],[44*mm,23*mm,26*mm,28*mm,50*mm])]

    story += [h1("Administration Reporting and Operations", "sec_admin"),
              h2("Verified deployment dashboard facts"), table([["Metric or check", "Observed value", "Operational meaning"],
                ["Documents", "4 total, 4 indexed", "Corpus is ready for retrieval"], ["Chunks", "28", "Indexed retrieval units"],
                ["Ingestion", "Inline per request", "Serverless ingestion runs during upload"], ["Database", "Schema version 5", "Database check passes"],
                ["Database persistence", "Turso healthy", "Identity and metadata are durable"], ["File persistence", "Failing readiness check", "Runtime files and vector changes are temporary"],
                ["Language model", "Not configured", "Responses use retrieval-only mode"], ["Embeddings", "Index matches configuration", "No reindex currently required"],
                ["OCR", "Tesseract unavailable", "Image uploads will fail"]],[47*mm,42*mm,82*mm]),
              h2("Reporting capabilities"), body("The product reports corpus counts, indexing state, chunk counts, recent documents, recent events, worker readiness, uptime, environment, dependency status, and LLM configuration status. It does not provide business analytics such as adoption trends, answer ratings, department usage, or retrieval-quality dashboards in the assessed build."),
              h2("Notifications and communication"), body("The application provides in-product status, validation, error, and health messages. No verified email, SMS, Slack, Teams, or push-notification integration exists in this deployment.")]

    story += [h1("Validation Error Handling and Troubleshooting", "sec_validation"),
              table([["Area", "Rule or condition", "Expected handling"],
                ["Sign in", "Missing or invalid credentials", "Remain on sign-in and show a safe error"],
                ["Employee", "Invalid email or duplicate ID/email", "Reject with a clear validation message"],
                ["Password", "Less than 8 or more than 256 characters", "Reject employee creation or update"],
                ["Message", "Empty or over 4,000 characters", "Reject without creating an orphan message"],
                ["Rate limit", "Too many messages from one client", "Return 429 and ask the user to wait"],
                ["Capacity", "No generation slot available", "Return service-busy response"],
                ["Upload", "Disallowed extension, oversize, signature mismatch, or duplicate", "Reject the affected file and report why"],
                ["Index", "Parser or embedding failure", "Mark document failed and preserve an event"],
                ["Provider", "LLM unavailable or unconfigured", "Return safe error or retrieval-only output"],
                ["Authorization", "Employee calls an admin endpoint", "Return HTTP 403"],
                ["Admin safety", "Delete or suspend final active administrator", "Return conflict and keep one active administrator"]],[36*mm,66*mm,69*mm]),
              h2("Troubleshooting sequence"),
              bullet("Confirm the account is active and the role badge is correct."), bullet("Check whether the expected document is indexed and assigned to the user or department."),
              bullet("Review health for database, ingestion, storage, persistence, LLM, embeddings, and OCR."), bullet("Open document details and events for parsing or indexing errors."),
              bullet("If configuration changed, reindex the affected document or all documents."), bullet("Test retrieval with a unique phrase from the intended document and verify the source chip."),
              bullet("For Vercel upload loss, confirm durable object and vector storage before repeating production ingestion.")]

    story += [h1("Security and Access Control", "sec_security"),
              table([["Control", "Verified implementation", "Assessment"],
                ["Authentication", "Employee email/password sessions", "Verified with four accounts"],
                ["Authorization", "Admin route enforcement", "Verified: employee admin requests return 403"],
                ["Password storage", "PBKDF2-HMAC-SHA256 with per-password salt", "Verified in source"],
                ["Cross-site protection", "CSRF token and same-origin checks on state changes", "Verified in source"],
                ["Security headers", "CSP, frame denial, nosniff, referrer and permissions policies", "Verified in deployment configuration"],
                ["Upload safety", "Allow list, size limits, content signatures, sanitized and generated names", "Verified in source"],
                ["Prompt-injection posture", "Retrieved text is treated as reference material", "Verified in source instructions"],
                ["Department scope", "Access assignments supported", "Not configured for the current corpus"],
                ["Secret handling", "Saved LLM key is not returned to browser", "Verified in source"],
                ["Data durability", "Turso durable; uploaded files/vector changes temporary", "Production gap"]],[39*mm,78*mm,54*mm]),
              body("Security conclusion: the application has a meaningful authentication and admin-authorization foundation, but the business promise of departmental knowledge isolation is not met by the current all-departments document assignments. Access metadata is security configuration and must be treated as part of the release gate.")]

    story += [h1("Benefits and Operational Value", "sec_benefits"),
              table([["Perspective", "Benefit", "Why it matters"],
                ["Employee", "Faster path from question to exact passage", "Reduces file-by-file search and supports follow-up questions"],
                ["Administrator", "Central document, user, access, model, and health controls", "Makes the service operable rather than opaque"],
                ["Manager", "Cited answers that can be reviewed in coaching and decisions", "Encourages consistent use of approved source material"],
                ["Business owner", "A single governed knowledge access layer", "Creates a foundation for scalable onboarding and internal support"],
                ["Organization", "Reusable conversations and auditable evidence", "Improves knowledge continuity without unsupported ROI claims"]],[36*mm,69*mm,66*mm]),
              h2("Operational improvements"), bullet("A source-first answer workflow makes disagreements easier to resolve."), bullet("Administrators can diagnose readiness from health and event data."), bullet("Retrieval-only fallback preserves limited utility when generation is disabled."), bullet("Explicit document access metadata creates a controllable path to departmental isolation once correctly configured."), bullet("Conversation history supports learning, onboarding, and repeated operational questions.")]

    story += [h1("Verified Findings and Recommendations", "sec_findings")]
    story += [table([["Priority", "Finding", "Evidence", "Recommended action"], *FINDINGS],[18*mm,39*mm,60*mm,54*mm], font_size=7.2)]
    story += [h2("Recommended release gate"), body("Do not describe the deployment as department-restricted until every document has an explicit intended access assignment and the positive/negative role tests in this handbook pass. Production readiness should also require durable file and vector storage, an approved LLM configuration or an intentional retrieval-only product decision, and clear handling for unsupported image OCR.")]

    story += [h1("Frequently Asked Questions", "sec_faq")]
    faqs = [
        ("Does the Copilot always generate a natural-language answer?", "No. The assessed deployment has no configured LLM, so it returns the most relevant passages in retrieval-only mode."),
        ("Can users inspect the evidence?", "Yes. Source chips show filenames and pages, and the source-detail view exposes the exact passages used."),
        ("Are employee accounts prevented from using admin APIs?", "Yes. HR, Finance, and Executive accounts returned HTTP 403 for the admin bootstrap endpoint."),
        ("Is departmental isolation working now?", "The mechanism exists, but the current four documents are assigned to all departments. The deployment therefore returns cross-department material."),
        ("What files can be uploaded?", "The parsers support common PDF, Word, Excel, image, JSON, and text formats, subject to the configured allow list and size limits."),
        ("What happens after an embedding change?", "The admin health and knowledge-base area can report that reindexing is required. Reindex the affected documents before relying on new retrieval behavior."),
        ("Are Vercel uploads durable?", "Not in the assessed build. Employee and metadata persistence use Turso, while uploaded originals and runtime vector changes remain temporary."),
        ("Can an administrator remove the last administrator?", "No. Validations prevent self-removal and preserve at least one active administrator account."),
    ]
    for q,a in faqs: story += [h2(q), body(a)]

    story += [h1("Glossary", "sec_glossary"), table([["Term", "Meaning"],
        ["RAG", "Retrieval-augmented generation: retrieve relevant passages, then use them to form or support an answer."],
        ["Chunk", "A segment of a document stored as a retrieval unit."], ["Embedding", "A numeric representation used to compare semantic similarity."],
        ["Vector index", "The store searched for document chunks related to a question."], ["Grounding", "Constraining an answer to retrieved evidence."],
        ["Source chip", "A selectable citation showing the document and pages used."], ["CSRF", "Protection that requires a server token and same-origin request for state changes."],
        ["Department scope", "Document access assigned to a department."], ["Retrieval-only mode", "Fallback that returns relevant passages when no language model is configured."],
        ["Turso", "The shared serverless SQLite service used for durable records in this deployment."], ["Reindex", "Reparse or re-embed content and replace its vector entries."]],[38*mm,133*mm])]

    story += [h1("Conclusion and Future Scope", "sec_conclusion"),
              body("BIZGENIX Knowledge Copilot already provides a coherent protected RAG workspace with source inspection and a substantial administration layer. Its strongest verified qualities are the clear employee experience, auditable citation flow, administrator authorization boundary, operational health visibility, and safe retrieval-only fallback."),
              body("The current deployment is not yet ready to support a claim of departmental isolation because every indexed document is assigned to all departments. Correcting access metadata and proving negative access tests is the immediate priority. Durable Vercel storage, model configuration, OCR strategy, and conversation-privacy decisions follow."),
              h2("Verified shipped capability"), bullet("Authenticated chat and administrator experiences."), bullet("Document retrieval, source chips, and passage inspection."), bullet("Conversation lifecycle and role context."), bullet("Document, employee, department, configuration, event, and health administration."),
              h2("Suggested future scope"), bullet("Default-deny document access and automated role-isolation regression tests."), bullet("Durable object storage and shared vector infrastructure."), bullet("Per-user or department-scoped conversation ownership."), bullet("Answer feedback, retrieval-quality evaluation, and usage analytics."), bullet("Supported OCR service and accessible mobile testing."), bullet("Release-readiness checklist with policy and audit exports."),
              Spacer(1,8*mm), body('<b>End of document</b>')]

    doc = HandbookDoc(str(PDF_PATH))
    doc.multiBuild(story)


def build_docx() -> None:
    from docx import Document
    from docx.enum.section import WD_SECTION
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Inches, Pt, RGBColor

    ensure_outputs()
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin, sec.right_margin, sec.top_margin, sec.bottom_margin = Cm(1.8), Cm(1.8), Cm(2.1), Cm(1.8)
    styles = doc.styles
    for name,size,color in [("Normal",10.5,CHARCOAL),("Title",28,"#000000"),("Heading 1",19,"#000000"),("Heading 2",13,"#000000"),("Heading 3",11,"#000000")]:
        st=styles[name]; st.font.name="Aptos"; st.font.size=Pt(size); st.font.color.rgb=RGBColor.from_string(color.lstrip("#"))
        st._element.rPr.rFonts.set(qn("w:ascii"),"Aptos"); st._element.rPr.rFonts.set(qn("w:hAnsi"),"Aptos")
    styles["Normal"].paragraph_format.space_after=Pt(6); styles["Normal"].paragraph_format.line_spacing=1.12
    styles["Heading 1"].paragraph_format.space_before=Pt(15); styles["Heading 1"].paragraph_format.space_after=Pt(7)
    styles["Heading 2"].paragraph_format.space_before=Pt(10); styles["Heading 2"].paragraph_format.space_after=Pt(4)
    styles["Heading 3"].paragraph_format.space_before=Pt(8); styles["Heading 3"].paragraph_format.space_after=Pt(3)

    def shade(cell, fill):
        tcPr=cell._tc.get_or_add_tcPr(); shd=OxmlElement("w:shd"); shd.set(qn("w:fill"),fill.lstrip("#")); tcPr.append(shd)
    def margins(cell, top=90, start=90, bottom=90, end=90):
        tc=cell._tc.get_or_add_tcPr(); m=tc.first_child_found_in("w:tcMar")
        if m is None: m=OxmlElement("w:tcMar"); tc.append(m)
        for tag,val in (("top",top),("start",start),("bottom",bottom),("end",end)):
            x=OxmlElement(f"w:{tag}"); x.set(qn("w:w"),str(val)); x.set(qn("w:type"),"dxa"); m.append(x)
    def set_repeat(row):
        trPr=row._tr.get_or_add_trPr(); el=OxmlElement("w:tblHeader"); el.set(qn("w:val"),"true"); trPr.append(el)
    def add_table(rows, widths=None):
        t=doc.add_table(rows=1, cols=len(rows[0])); t.alignment=WD_TABLE_ALIGNMENT.CENTER; t.style="Table Grid"
        hdr=t.rows[0]; set_repeat(hdr)
        for i,v in enumerate(rows[0]):
            hdr.cells[i].text=str(v); shade(hdr.cells[i],FOREST); hdr.cells[i].vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            for r in hdr.cells[i].paragraphs[0].runs: r.font.bold=True; r.font.color.rgb=RGBColor(255,255,255); r.font.size=Pt(8.5)
        for ri,row in enumerate(rows[1:],1):
            cells=t.add_row().cells
            for i,v in enumerate(row):
                cells[i].text=str(v); cells[i].vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER; margins(cells[i])
                if ri%2==0: shade(cells[i],PALE)
                for p in cells[i].paragraphs:
                    for r in p.runs: r.font.size=Pt(8.2); r.font.color.rgb=RGBColor.from_string(CHARCOAL.lstrip("#"))
        if widths:
            for row in t.rows:
                for i,w in enumerate(widths): row.cells[i].width=Cm(w)
        doc.add_paragraph()
        return t
    def add_img(filename, caption):
        path=SHOTS/filename
        if path.exists():
            p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.add_run().add_picture(str(path),width=Cm(17.2))
            c=doc.add_paragraph(caption); c.alignment=WD_ALIGN_PARAGRAPH.CENTER
            for r in c.runs: r.font.size=Pt(8); r.font.color.rgb=RGBColor.from_string(GREY.lstrip("#")); r.font.italic=True
    def heading(text, level=1): doc.add_heading(text, level=level)
    def para(text,bold_lead=None):
        p=doc.add_paragraph()
        if bold_lead: p.add_run(bold_lead).bold=True
        p.add_run(text); return p
    def bullets(items):
        for item in items: doc.add_paragraph(item,style="List Bullet")

    logo=ROOT/"public"/"static"/"img"/"bizgenix-logo.png"
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    if logo.exists(): p.add_run().add_picture(str(logo),width=Cm(6))
    title=doc.add_paragraph("Knowledge Copilot",style="Title"); title.alignment=WD_ALIGN_PARAGRAPH.CENTER
    sub=doc.add_paragraph("Complete Product Documentation"); sub.alignment=WD_ALIGN_PARAGRAPH.CENTER
    for r in sub.runs: r.font.size=Pt(18); r.font.bold=True; r.font.color.rgb=RGBColor.from_string(FOREST.lstrip("#"))
    meta=doc.add_paragraph("Role-based AI RAG system\nDeployment assessed 21 November 2026\nDocument version 1.0"); meta.alignment=WD_ALIGN_PARAGRAPH.CENTER
    doc.add_page_break()

    heading("Document Control")
    add_table([["Field","Value"],["Document","BIZGENIX Knowledge Copilot Complete Product Documentation"],["Version","1.0"],["Assessment date","21 November 2026"],["Application","https://rag-two-ivory.vercel.app/"],["Company","BIZGENIX AI"],["Evidence basis","Deployed UI, authenticated APIs, application source, and health checks"]],[4,13])
    para("This handbook describes the deployed product, user and administrator workflows, business value, current limitations, and recommendations. Verified behavior is separated from suggested future scope.")
    heading("Table of Contents")
    for i,(name,_) in enumerate(SECTIONS,1): doc.add_paragraph(f"{i}. {name}")
    doc.add_page_break()

    heading("Executive Summary")
    para("BIZGENIX Knowledge Copilot is an authenticated document question-answering product with employee and administrator roles. Employees ask questions, retain conversation history, and inspect source passages. Administrators manage documents, access assignments, employees, departments, indexing, language-model configuration, events, and service health.")
    para("The assessed deployment is operational in retrieval-only mode. Authentication and administrator authorization work, four documents are indexed into 28 chunks, and employee admin API requests are rejected. The most important readiness gap is that every document is assigned to all departments, so the deployment does not yet demonstrate departmental knowledge isolation.")
    add_table([["Indexed documents","Indexed chunks","Active test accounts","Configured LLMs"],["4","28","4","0"]],[4.2,4.2,4.2,4.2])

    heading("Product Introduction")
    para("The product provides a branded internal knowledge workspace that combines protected employee access, a conversational interface, document retrieval, source inspection, persistent conversation history, and an administrator control plane.")
    heading("Product Vision",2); para("Give the right employee a fast, understandable, and traceable way to use company knowledge while administrators retain control over people, documents, access scope, indexing, and model configuration.")
    heading("Verified objectives",2); bullets(["Require authentication before protected application access.","Expose employee role and department context.","Retrieve document passages and attach source metadata.","Preserve conversations for follow-up work.","Provide governed ingestion and operational visibility.","Degrade to retrieval-only output when no language model is configured."])

    heading("Vision Objectives and Business Problems")
    add_table([["Problem","Product response","Business effect"],["Knowledge is spread across files","Conversational retrieval","Less manual browsing"],["Answers are hard to verify","Source chips and exact passages","Faster review and correction"],["Sensitive knowledge needs governance","Authentication, roles, and access assignments","A basis for controlled distribution"],["Content changes over time","Upload, status, reindex, and events","Operational control"],["AI service is unavailable","Retrieval-only fallback","Basic lookup remains available"]],[4.4,6.3,6.2])

    heading("Audience and Personas")
    add_table([["Persona","Primary need","Typical tasks","Success signal"],["Department employee","Answers within permitted knowledge","Ask, inspect sources, reopen history","Relevant evidence without admin exposure"],["Administrator","Governed and healthy service","Manage content, access, people, and health","Indexed content and controlled access"],["Manager","Trusted team references","Review answers and coach workflows","Consistent use of approved sources"],["Business owner","Readiness and adoption visibility","Review risks and value","Known limitations and ownership"]],[3.3,4.5,5.3,4.0])
    para("Manager and business-owner perspectives are stakeholder personas, not separately verified UI roles.")

    heading("Product Overview")
    add_img("01_login.png","Figure 1. Protected BIZGENIX sign-in.")
    add_table([["Area","Purpose","Verified elements"],["Sign in","Authenticate users","Email, password, secure-workspace message"],["Chat workspace","Ask and refine questions","Role badge, RAG indicator, suggestions, composer"],["Conversation sidebar","Return to research","New, recent, rename, delete, delete all"],["Answer view","Review output","Retrieved passages, sources, copy, regenerate"],["Source detail","Inspect evidence","Filename, pages, exact excerpts"],["Admin workspace","Operate the service","Documents, people, settings, events, health"]],[3.7,5.1,8.2])
    add_img("02_hr_workspace.png","Figure 2. HR employee workspace with role context, suggestions, recent conversations, and composer.")

    heading("Module and Feature Documentation")
    para("Each feature uses a consistent product-documentation pattern and identifies its verification status.")
    for item in FEATURES:
        heading(item["name"],2)
        add_table([["Field","Detail"],["Feature overview",item["overview"]],["Purpose",item["purpose"]],["Business problem",item["problem"]],["Key functionality",item["functions"]],["How to use",item["steps"]],["Inputs and outputs",item["io"]],["Roles",item["roles"]],["Rules and validations",item["rules"]],["Expected result",item["result"]],["Use case",item["use"]],["Benefits",item["benefit"]],["Verification",item["status"]]],[4.0,13.0])
    add_img("03_hr_retrieval_response.png","Figure 3. Retrieval-only response with source evidence and current cross-department scope.")
    add_img("04_about_rag.png","Figure 4. In-product explanation of RAG and source inspection.")
    add_img("05_source_detail.png","Figure 5. Source-detail view with exact pages and passages.")

    heading("User Guides and Workflows")
    heading("Employee quick start",2)
    for n,t in enumerate(["Open the deployment and sign in.","Confirm the department badge.","Select a suggestion or enter a focused question.","Review the answer and Sources section.","Open source chips and inspect exact passages.","Ask a follow-up, copy, regenerate, or reopen from Recent.","Sign out on shared devices."],1): para(t,f"{n}. ")
    heading("Administrator document onboarding",2)
    for n,t in enumerate(["Confirm intended access scope.","Choose a supported file.","Assign department or named employees explicitly.","Upload and monitor status.","Inspect document details and chunks.","Run positive and negative role tests.","Record results before production use."],1): para(t,f"{n}. ")

    heading("Architecture and Data Flow")
    para("Browser requests reach the Vercel Python application. It coordinates authentication, conversations, document administration, retrieval, and an optional model provider. Turso stores durable identity and metadata records. Runtime file and vector changes remain temporary on Vercel.")
    add_table([["Layer","Verified component","Responsibility"],["Client","Browser UI","Sign in, chat, sources, administration"],["Application","Vercel Python runtime","Routing, checks, streaming, orchestration"],["Identity","Session and role services","Authentication and authorization"],["Data","Turso database","Employees, departments, sessions, permissions, history, metadata"],["Knowledge","Parsers and vector index","Chunk, embed, retrieve"],["AI","Optional LLM provider","Grounded answer generation when enabled"]],[3.6,5.7,7.6])
    heading("Document ingestion flow",2); para("Uploads are validated, deduplicated, stored under generated names, parsed into chunks, embedded, and atomically swapped into the index. Failed processing records an administrator-visible error.")

    heading("Roles Permissions and Access")
    add_table([["Role","Employee functions","Admin functions","Assessment note"],*ROLE_ROWS],[3.8,4.8,4.2,4.2])
    heading("Current departmental access gap",2); para("All indexed documents are assigned to all departments. Each supplied department account therefore receives the same suggestions and cross-department retrieval. The access mechanism exists, but isolation is not configured in the current corpus.")
    add_table([["Test","HR","Finance","Executive","Expected"],["HR-only document","Allow","Deny","Deny","Only HR source"],["Finance-only document","Deny","Allow","Deny","Only Finance source"],["Executive-only document","Deny","Deny","Allow","Only Executive source"],["Admin API","Deny","Deny","Deny","HTTP 403"]],[4.3,2.2,2.5,2.7,5.3])

    heading("Administration Reporting and Operations")
    add_table([["Metric or check","Observed value","Operational meaning"],["Documents","4 total, 4 indexed","Corpus ready for retrieval"],["Chunks","28","Indexed retrieval units"],["Database persistence","Turso healthy","Identity and metadata durable"],["File persistence","Readiness check fails","Files and vector changes temporary"],["Language model","Not configured","Retrieval-only mode"],["Embeddings","Index matches","No reindex required"],["OCR","Unavailable","Image uploads will fail"]],[4.7,4.2,8.0])
    para("The product reports corpus counts, ingestion state, events, worker readiness, uptime, dependency status, and model configuration. Business adoption and answer-quality analytics are not present in the assessed build.")

    heading("Validation Error Handling and Troubleshooting")
    add_table([["Area","Rule or condition","Expected handling"],["Sign in","Invalid credentials","Safe error and no protected access"],["Employee","Duplicate ID/email or invalid email","Reject with validation message"],["Password","Outside 8-256 characters","Reject update"],["Message","Empty or over 4,000 characters","Reject without orphan message"],["Rate","Too many messages","HTTP 429"],["Capacity","No generation slot","Service busy"],["Upload","Type, size, signature, or duplicate failure","Reject affected file"],["Index","Parser or embedding failure","Mark failed and log event"],["Provider","Disabled","Retrieval-only output"],["Authorization","Employee uses admin endpoint","HTTP 403"]],[3.5,6.5,7.0])
    bullets(["Confirm the active role and department.","Check the document status and access assignment.","Review service health and events.","Reindex after relevant configuration changes.","Test a unique document phrase and inspect its source.","Confirm durable storage before production uploads on Vercel."])

    heading("Security and Access Control")
    add_table([["Control","Verified implementation","Assessment"],["Authentication","Employee sessions","Verified with four accounts"],["Authorization","Admin route checks","Employee requests return 403"],["Passwords","PBKDF2-HMAC-SHA256 with salt","Verified in source"],["CSRF","Token and same-origin checks","Verified in source"],["Headers","CSP, frame denial, nosniff","Verified in deployment"],["Uploads","Allow list, limits, signatures, generated names","Verified in source"],["Secret handling","Saved model key not returned","Verified in source"],["Department scope","Supported through assignments","Not configured for corpus"],["Durability","Turso durable; files/vector changes temporary","Production gap"]],[3.8,8.0,5.2])

    heading("Benefits and Operational Value")
    add_table([["Perspective","Benefit","Why it matters"],["Employee","Faster question-to-passage path","Reduces manual search"],["Administrator","Central operational controls","Makes the service operable"],["Manager","Cited reviewable answers","Supports consistent coaching"],["Business owner","Governed knowledge layer","Foundation for scalable onboarding"],["Organization","Reusable history and evidence","Improves continuity without unsupported ROI claims"]],[3.6,6.4,7.0])

    heading("Verified Findings and Recommendations")
    add_table([["Priority","Finding","Evidence","Recommended action"],*FINDINGS],[1.7,3.8,6.0,5.4])
    para("Do not describe the deployment as department-restricted until explicit access assignments and negative role tests pass. Production readiness also requires durable file/vector storage and an intentional model and OCR strategy.")

    heading("Frequently Asked Questions")
    for q,a in [("Does the Copilot always generate a natural-language answer?","No. The assessed deployment uses retrieval-only mode."),("Can users inspect evidence?","Yes. Source chips expose filenames, pages, and passages."),("Are employee accounts blocked from admin APIs?","Yes. The supplied employee accounts returned HTTP 403."),("Is departmental isolation working now?","No. All current documents are assigned to all departments."),("Are Vercel uploads durable?","No. Uploaded originals and runtime vector changes remain temporary."),("Can the final active administrator be removed?","No. Validations preserve at least one active administrator.")]:
        heading(q,2); para(a)

    heading("Glossary")
    add_table([["Term","Meaning"],["RAG","Retrieve relevant passages, then use them to form or support an answer."],["Chunk","A segment stored as a retrieval unit."],["Embedding","A numeric representation used for semantic similarity."],["Vector index","The store searched for related chunks."],["Grounding","Constraining output to retrieved evidence."],["Source chip","A selectable citation showing document and pages."],["CSRF","A token and same-origin protection for state changes."],["Retrieval-only mode","Fallback that returns passages without model generation."],["Turso","Shared serverless SQLite used for durable records."],["Reindex","Reparse or re-embed content and replace vector entries."]],[3.8,13.2])

    heading("Conclusion and Future Scope")
    para("BIZGENIX Knowledge Copilot provides a coherent protected RAG workspace with source inspection and a substantial administration layer. Its strongest verified qualities are the employee experience, auditable citation flow, admin authorization boundary, health visibility, and retrieval-only fallback.")
    para("The immediate release priority is to configure document access and prove departmental isolation. Durable storage, model configuration, OCR strategy, conversation ownership, usage analytics, and automated retrieval evaluation follow as suggested future scope.")
    heading("Suggested future scope",2); bullets(["Default-deny document access and automated role tests.","Durable object and vector storage.","Per-user or department-scoped conversation ownership.","Answer feedback and retrieval evaluation.","Supported OCR and mobile accessibility testing.","Release-readiness and audit exports."])

    footer=sec.footer.paragraphs[0]; footer.alignment=WD_ALIGN_PARAGRAPH.CENTER
    run=footer.add_run("BIZGENIX AI Knowledge Copilot | Product Documentation")
    run.font.size=Pt(8); run.font.color.rgb=RGBColor.from_string(GREY.lstrip("#"))
    doc.core_properties.title="BIZGENIX Knowledge Copilot Complete Product Documentation"
    doc.core_properties.subject="Role-based AI RAG system product handbook"
    doc.core_properties.author="BIZGENIX AI"
    doc.save(DOCX_PATH)


if __name__ == "__main__":
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "all"
    write_supporting_files()
    if mode in ("pdf", "all"):
        build_pdf()
    if mode in ("docx", "all"):
        build_docx()
    print(f"Built {mode} artifacts in {OUT}")
