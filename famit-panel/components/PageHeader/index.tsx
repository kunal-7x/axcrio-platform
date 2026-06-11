// Unified page masthead — NEUTRALIZED to the reference kit (W1, design/
// ui-font-heading-plan.md §4 + ui-design-principles.md).
//
// The founder's explicit fix: a page title is a SINGLE clean line — no eyebrow,
// no animated signal glyph, no brand-blue accent rule, NO subtitle/description.
// That over-decorated masthead was the "too complex / jargon" clutter he rejects.
//
// This component now renders ONLY the reference header: the title at
// `text-h4 max-lg:text-h5` (matching components/Header's sticky title) plus an
// optional right-aligned actions slot. The `eyebrow` and `subtitle` props are
// kept in the type (so existing callers still compile) but are intentionally
// IGNORED — page agents can drop those props at their own pace without breaking
// the build. The canonical page title is the reference <Layout title="…">.

type PageHeaderProps = {
    title: string;
    /** @deprecated ignored — reference headers have no eyebrow. */
    eyebrow?: string;
    /** @deprecated ignored — reference headers have no subtitle. */
    subtitle?: React.ReactNode;
    actions?: React.ReactNode;
    className?: string;
};

const PageHeader = ({ title, actions, className }: PageHeaderProps) => (
    <div
        className={`flex items-start justify-between gap-4 mb-6 max-md:mb-4 ${
            className || ""
        }`}
    >
        <h1 className="text-h4 max-lg:text-h5 text-t-primary">{title}</h1>
        {actions && (
            <div className="flex items-center gap-3 shrink-0 max-md:hidden">
                {actions}
            </div>
        )}
    </div>
);

export default PageHeader;
