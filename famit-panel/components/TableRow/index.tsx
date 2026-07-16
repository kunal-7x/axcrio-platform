import Checkbox from "@/components/Checkbox";

type RowProps = {
    className?: string;
    selectedRows?: boolean;
    onRowSelect?: (enabled: boolean) => void;
    children: React.ReactNode;
    onClick?: () => void;
};

const Row = ({
    className,
    selectedRows,
    onRowSelect,
    children,
    onClick,
}: RowProps) => {
    return (
        <tr
            className={`group relative [&_td:not(:first-child)]:relative [&_td]:z-2 [&_td]:border-t [&_td]:border-s-subtle max-md:first:[&_td]:border-t-0 ${
                onRowSelect
                    ? "[&_td]:transition-colors hover:[&_td]:bg-b-highlight hover:[&_td]:border-transparent hover:[&_+tr]:[&_td]:border-transparent"
                    : ""
            } ${className || ""}`}
            onClick={onClick}
        >
            {onRowSelect && (
                <td className="w-10 max-lg:w-9 max-md:hidden">
                    {/* NOTE: the old `.box-hover` absolute overlay escaped the row in
                        Safari (tr position:relative isn't a containing block there) and
                        covered the whole card on hover. Replaced with a cell-bg hover. */}
                    <Checkbox
                        classTick="dark:group-hover:border-s-highlight"
                        checked={selectedRows || false}
                        onChange={onRowSelect}
                    />
                </td>
            )}
            {children}
        </tr>
    );
};

export default Row;
