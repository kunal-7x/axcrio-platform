"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Search from "@/components/Search";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import Icon from "@/components/Icon";
import { getCompanies, type Company, type ActivityTarget } from "../client";
import { fmtRelative } from "../_ui";

export default function CompaniesView({
    onOpen,
}: {
    canWrite: boolean;
    onOpen: (type: ActivityTarget, id: string) => void;
}) {
    const [query, setQuery] = useState("");
    const [debounced, setDebounced] = useState("");
    useEffect(() => {
        const t = setTimeout(() => setDebounced(query.trim()), 280);
        return () => clearTimeout(t);
    }, [query]);

    const q = useQuery({
        queryKey: ["twenty", "companies", debounced],
        queryFn: () => getCompanies({ q: debounced, limit: 50 }),
        refetchInterval: 30_000,
    });

    const rows: Company[] = q.data?.companies ?? [];
    // instant client filter on top of the loaded page so typing feels live
    const visible = useMemo(() => {
        const s = query.trim().toLowerCase();
        if (!s) return rows;
        return rows.filter(
            (c) => c.name.toLowerCase().includes(s) || c.domain.toLowerCase().includes(s)
        );
    }, [rows, query]);

    return (
        <div>
            <div className="px-2 pb-3 max-lg:px-1">
                <Search
                    className="w-80 max-md:w-full"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search companies"
                    isGray
                />
            </div>
            {q.isLoading ? (
                <ListSkeleton cols={4} />
            ) : visible.length === 0 ? (
                <Empty query={query} label="companies" hint="Companies you add (or import) appear here." />
            ) : (
                <Table
                    cellsThead={
                        <>
                            <th>Company</th>
                            <th className="max-md:hidden">People</th>
                            <th className="max-md:hidden">Deals</th>
                            <th className="max-lg:hidden">Location</th>
                            <th className="text-right max-md:hidden">Added</th>
                        </>
                    }
                >
                    {visible.map((c) => (
                        <TableRow
                            key={c.id}
                            className="cursor-pointer [&_td]:transition-colors hover:[&_td]:bg-b-highlight"
                            onClick={() => onOpen("company", c.id)}
                        >
                            <td className="font-medium text-t-primary">
                                <div className="flex items-center gap-3">
                                    <span className="grid place-items-center size-10 shrink-0 rounded-2xl bg-b-surface1 text-t-secondary">
                                        <Icon name="bag" className="size-4.5 fill-t-secondary" />
                                    </span>
                                    <span className="min-w-0">
                                        <span className="block truncate max-w-56 text-sub-title-1 text-t-primary">
                                            {c.name}
                                        </span>
                                        <span className="block truncate max-w-56 text-body-2 text-t-tertiary">
                                            {c.domain || "—"}
                                        </span>
                                    </span>
                                </div>
                            </td>
                            <td className="text-t-secondary max-md:hidden">{c.peopleCount ?? "—"}</td>
                            <td className="text-t-secondary max-md:hidden">{c.opportunitiesCount ?? "—"}</td>
                            <td className="text-t-secondary max-lg:hidden">
                                {[c.city, c.country].filter(Boolean).join(", ") || "—"}
                            </td>
                            <td className="text-t-secondary text-right max-md:hidden">
                                {fmtRelative(c.createdAt)}
                            </td>
                        </TableRow>
                    ))}
                </Table>
            )}
        </div>
    );
}

export function ListSkeleton({ cols }: { cols: number }) {
    return (
        <Table cellsThead={[...Array(cols)].map((_, i) => <th key={i} />)}>
            {[...Array(6)].map((_, i) => (
                <TableRow key={i}>
                    {[...Array(cols)].map((__, j) => (
                        <td key={j}>
                            <div className={`skeleton h-4 rounded-lg ${j === 0 ? "w-48" : "w-20"}`} />
                        </td>
                    ))}
                </TableRow>
            ))}
        </Table>
    );
}

export function Empty({ query, label, hint }: { query: string; label: string; hint: string }) {
    return (
        <div className="py-16 text-center max-md:py-12">
            <span className="inline-grid place-items-center size-14 mb-4 rounded-full bg-b-surface1">
                <Icon name={query ? "search" : "profile"} className="fill-t-tertiary" />
            </span>
            <div className="text-h6 mb-1">{query ? `No matching ${label}` : `No ${label} yet`}</div>
            <div className="max-w-md mx-auto text-body-2 text-t-secondary">
                {query ? `Nothing matches “${query}”.` : hint}
            </div>
        </div>
    );
}
