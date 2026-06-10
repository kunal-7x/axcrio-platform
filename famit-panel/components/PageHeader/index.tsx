// Unified page masthead (premium-ui wave 2 — "Signal").
//
// ONE header rhythm for every page: a brand-blue accent rule, an overline
// eyebrow, the title, an optional subtitle, and a right-aligned action slot.
// Presentational only — pages keep passing their own title via <Layout> for
// the sticky header; this renders the in-page masthead so all pages share a
// precise, premium top section instead of bare template chrome.

type PageHeaderProps = {
    title: string;
    eyebrow?: string;
    subtitle?: React.ReactNode;
    actions?: React.ReactNode;
    className?: string;
};

const PageHeader = ({
    title,
    eyebrow,
    subtitle,
    actions,
    className,
}: PageHeaderProps) => (
    <div className={`page-head rise-in ${className || ""}`}>
        <div className="min-w-0 flex-1">
            {eyebrow && (
                <div className="page-head-eyebrow">
                    <span className="signal-glyph !h-3" aria-hidden>
                        <i />
                        <i />
                        <i />
                    </span>
                    {eyebrow}
                </div>
            )}
            <h1 className="page-head-title">{title}</h1>
            {subtitle && <p className="page-head-sub">{subtitle}</p>}
        </div>
        {actions && (
            <div className="flex items-center gap-3 shrink-0 pt-1 max-md:hidden">
                {actions}
            </div>
        )}
    </div>
);

export default PageHeader;
