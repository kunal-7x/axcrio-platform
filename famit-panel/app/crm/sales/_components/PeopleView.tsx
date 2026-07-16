"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Search from "@/components/Search";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import { getPeople, type Person, type ActivityTarget } from "../client";
import { Avatar, fmtRelative } from "../_ui";
import { ListSkeleton, Empty } from "./CompaniesView";

export default function PeopleView({
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
        queryKey: ["twenty", "people", debounced],
        queryFn: () => getPeople({ q: debounced, limit: 50 }),
        refetchInterval: 30_000,
    });

    const rows: Person[] = q.data?.people ?? [];
    const visible = useMemo(() => {
        const s = query.trim().toLowerCase();
        if (!s) return rows;
        return rows.filter(
            (p) =>
                p.name.toLowerCase().includes(s) ||
                p.email.toLowerCase().includes(s) ||
                p.phone.toLowerCase().includes(s)
        );
    }, [rows, query]);

    return (
        <div>
            <div className="px-2 pb-3 max-lg:px-1">
                <Search
                    className="w-80 max-md:w-full"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search people by name, email or phone"
                    isGray
                />
            </div>
            {q.isLoading ? (
                <ListSkeleton cols={4} />
            ) : visible.length === 0 ? (
                <Empty
                    query={query}
                    label="people"
                    hint="Import your called leads, or add a contact — they show up here."
                />
            ) : (
                <Table
                    cellsThead={
                        <>
                            <th>Person</th>
                            <th className="max-md:hidden">Phone</th>
                            <th className="max-lg:hidden">Company</th>
                            <th className="max-lg:hidden">Title</th>
                            <th className="text-right max-md:hidden">Added</th>
                        </>
                    }
                >
                    {visible.map((p) => (
                        <TableRow
                            key={p.id}
                            className="cursor-pointer [&_td]:transition-colors hover:[&_td]:bg-b-highlight"
                            onClick={() => onOpen("person", p.id)}
                        >
                            <td className="font-medium text-t-primary">
                                <div className="flex items-center gap-3">
                                    <Avatar name={p.name} url={p.avatarUrl} />
                                    <span className="min-w-0">
                                        <span className="block truncate max-w-56 text-sub-title-1 text-t-primary">
                                            {p.name}
                                        </span>
                                        <span className="block truncate max-w-56 text-body-2 text-t-tertiary">
                                            {p.email || "—"}
                                        </span>
                                    </span>
                                </div>
                            </td>
                            <td className="text-t-secondary max-md:hidden">{p.phone || "—"}</td>
                            <td className="text-t-secondary max-lg:hidden">{p.companyName || "—"}</td>
                            <td className="text-t-secondary max-lg:hidden">{p.jobTitle || "—"}</td>
                            <td className="text-t-secondary text-right max-md:hidden">
                                {fmtRelative(p.createdAt)}
                            </td>
                        </TableRow>
                    ))}
                </Table>
            )}
        </div>
    );
}
