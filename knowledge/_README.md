# Knowledge Folder

Add your business knowledge here as `.md`, `.txt`, or `.csv` files. Files whose
names start with `_` are ignored, so this README is not used by the agent.

Good files to add:

- `company.md`: what Capsy/Vobiz/Aqulia does, contact details, escalation rules.
- `faq.md`: common caller questions and approved short answers.
- `sales_script.md`: qualification questions, objection handling, next steps.
- `properties.csv` or `projects.md`: inventory, city, budget, amenities, contact owner.

Keep answers phone-friendly. The agent works best when each fact is short and
explicit, for example:

```md
# Mumbai Flat Leads

For Mumbai flat buyers, first ask budget, preferred area, BHK, possession
timeline, and whether they want new launch or resale.

If the caller asks for the best area, ask their budget first because Bandra,
Andheri, Thane, Navi Mumbai, and Powai fit very different budgets.
```
