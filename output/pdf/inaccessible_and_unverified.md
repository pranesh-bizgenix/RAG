# Inaccessible and unverified functionality

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
