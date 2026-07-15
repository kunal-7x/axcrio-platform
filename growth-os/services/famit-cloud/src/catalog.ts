/**
 * Famit Cloud Catalog — the "marketplace" of provisionable things the cloud can stand up:
 *   • AGENTS    — a generated fleet of 1000s of role × industry agent templates.
 *   • DATABASES — engines we can run as containers (real: postgres/mysql/redis/… images).
 *   • DOMAINS   — TLDs + indicative pricing (availability is checked live via RDAP in providers.ts).
 *   • HOSTING   — site/app runtime plans (deployed as container workloads).
 *
 * The agent catalog is generated deterministically (no Math.random — stable ids across restarts) by
 * crossing a role taxonomy with an industry list, so "1000s of agents" is literal, browsable data —
 * each one deployable onto the workload supervisor.
 */

import type { RlDomain } from './feedback.js';

export type AgentTier = 'reasoning' | 'bulk' | 'cheap';

export interface AgentTemplate {
  id: string;
  name: string;
  category: string;
  role: string;
  industry: string;
  description: string;
  tools: string[];
  tier: AgentTier;
}

/** A curated, hireable AI employee: a catalog agent with a job description, KPIs and a salary.
 *  Hiring one goes through the SAME provision path as any agent (id resolvable by agentById), but
 *  is salary-metered at hire (kind 'salary', gated by the Budget Governor) and every completed
 *  inbox task is outcome-metered (kind 'outcome') — the unit of value the business actually buys. */
export interface WorkforceRole extends AgentTemplate {
  jd: string;
  kpis: string[];
  salaryInrMonth: number;
  outcomeKind: string;
  domain: RlDomain;
  everyMs: number;
}

const WORKFORCE: WorkforceRole[] = [
  {
    id: 'wf-sdr', name: 'AI SDR — WhatsApp lead follow-up', category: 'Workforce', role: 'SDR',
    industry: 'cross-industry', tier: 'bulk', tools: ['whatsapp', 'crm', 'email'], domain: 'whatsapp',
    everyMs: 5 * 60_000, salaryInrMonth: 4999, outcomeKind: 'lead_touched',
    description: 'Works your inbound leads 24/7 on WhatsApp — first touch in minutes, every follow-up on time.',
    jd: 'Owns the top of your funnel: picks up every new lead from the inbox, sends the first WhatsApp touch within minutes, runs the follow-up cadence, qualifies interest and books meetings straight into the calendar.',
    kpis: ['leads touched/day', 'replies converted', 'meetings booked'],
  },
  {
    id: 'wf-collections', name: 'AI Collections Agent — invoice chasing', category: 'Workforce', role: 'Collections Agent',
    industry: 'cross-industry', tier: 'reasoning', tools: ['payments', 'ledger', 'whatsapp'], domain: 'payments',
    everyMs: 10 * 60_000, salaryInrMonth: 5999, outcomeKind: 'invoice_chased',
    description: 'Chases every overdue invoice politely and relentlessly until the money lands.',
    jd: 'Watches your receivables, sequences polite-but-firm reminders per overdue invoice, negotiates promise-to-pay dates within your rules, and escalates only the accounts that truly need a human.',
    kpis: ['invoices chased/day', 'promises-to-pay won', '₹ recovered'],
  },
  {
    id: 'wf-support', name: 'AI Support Rep — Tier-1, WhatsApp + email', category: 'Workforce', role: 'Tier-1 Support',
    industry: 'cross-industry', tier: 'bulk', tools: ['whatsapp', 'email', 'kb'], domain: 'crm',
    everyMs: 5 * 60_000, salaryInrMonth: 3999, outcomeKind: 'ticket_resolved',
    description: 'Answers routine customer questions instantly, around the clock, from your own knowledge.',
    jd: 'Handles Tier-1: answers product/order/policy questions from your knowledge base, resolves routine tickets end-to-end, keeps the customer informed, and hands Tier-2 cases to your team with full context.',
    kpis: ['tickets resolved', 'first-response time', 'handoffs w/ context'],
  },
  {
    id: 'wf-ads', name: 'AI Ads Optimizer — campaign tuning', category: 'Workforce', role: 'Campaign Planner',
    industry: 'cross-industry', tier: 'reasoning', tools: ['ads', 'analytics'], domain: 'campaigns',
    everyMs: 15 * 60_000, salaryInrMonth: 6999, outcomeKind: 'campaign_tuned',
    description: 'Reviews your ad spend daily and reallocates budget from losers to winners.',
    jd: 'Audits campaign performance on a daily loop: kills wasted spend, shifts budget to winning ad sets, proposes copy refreshes, and reports the CTR and CAC movement it drove — money moves need your approval.',
    kpis: ['campaigns tuned', 'CTR lift', 'wasted spend cut'],
  },
  {
    id: 'wf-bookkeeper', name: 'AI Bookkeeper — daily ledger + reconciliation', category: 'Workforce', role: 'Reconciliation Agent',
    industry: 'cross-industry', tier: 'cheap', tools: ['ledger', 'sheets'], domain: 'payments',
    everyMs: 30 * 60_000, salaryInrMonth: 2999, outcomeKind: 'ledger_reconciled',
    description: 'Keeps the books current every single day — entries posted, mismatches flagged.',
    jd: 'Posts the day’s transactions to the ledger, reconciles bank and payment-gateway settlements against invoices, flags mismatches with evidence, and keeps a clean audit trail your accountant will love.',
    kpis: ['entries reconciled/day', 'mismatches caught', 'days books current'],
  },
  {
    id: 'wf-caller', name: 'AI Appointment Setter — outbound reminders', category: 'Workforce', role: 'Appointment Setter',
    industry: 'cross-industry', tier: 'bulk', tools: ['calls', 'crm'], domain: 'calls',
    everyMs: 10 * 60_000, salaryInrMonth: 5499, outcomeKind: 'appointment_set',
    description: 'Places reminder and booking calls so your calendar stays full and no-shows drop.',
    jd: 'Works the call list: confirms tomorrow’s appointments, re-books cancellations, reactivates cold leads with a courteous script, and logs every disposition back to the CRM. Voice runs on India-side substrate per placement law.',
    kpis: ['calls placed', 'appointments set', 'no-shows reduced'],
  },
];

export interface DbEngine {
  id: string;
  name: string;
  image: string;
  port: number;
  /** Env the container needs; values may be filled/﹡generated at provision time. */
  env: Record<string, string>;
  /** How to build a connection string given host/port/secret. */
  scheme: string;
  /** In-container data directory — mounted to a named volume so data survives restarts. */
  dataDir: string;
}

export interface DomainTld {
  tld: string;
  priceInrYear: number;
  popular?: boolean;
}

export interface HostingPlan {
  id: string;
  name: string;
  runtime: 'static' | 'node' | 'container';
  description: string;
  defaultImage?: string;
  port: number;
}

// ---- agent taxonomy → 1000s of templates ----------------------------------------------------

interface RoleGroup {
  category: string;
  roles: string[];
  tools: string[];
  tier: AgentTier;
}

const TAXONOMY: RoleGroup[] = [
  { category: 'Revenue', tier: 'bulk', tools: ['calls', 'whatsapp', 'crm', 'email'], roles: ['SDR', 'Account Executive', 'Closer', 'Lead Qualifier', 'Renewal Manager', 'Upsell Specialist', 'Win-back Agent'] },
  { category: 'Support', tier: 'bulk', tools: ['whatsapp', 'email', 'crm', 'kb'], roles: ['Tier-1 Support', 'Tier-2 Support', 'Onboarding Guide', 'Escalation Manager', 'CSAT Surveyor', 'KB Writer'] },
  { category: 'Marketing', tier: 'bulk', tools: ['ads', 'content', 'analytics', 'email'], roles: ['Campaign Planner', 'Ad Copywriter', 'SEO Strategist', 'Social Scheduler', 'Influencer Scout', 'Email Nurturer'] },
  { category: 'Operations', tier: 'cheap', tools: ['workflows', 'calendar', 'alerts'], roles: ['Scheduler', 'Dispatch Coordinator', 'Inventory Watcher', 'SLA Monitor', 'Workflow Orchestrator', 'Incident Responder'] },
  { category: 'Finance', tier: 'reasoning', tools: ['ledger', 'payments', 'sheets'], roles: ['Invoice Chaser', 'Reconciliation Agent', 'Expense Auditor', 'Pricing Analyst', 'Collections Agent', 'Budget Forecaster'] },
  { category: 'Data', tier: 'bulk', tools: ['sql', 'sheets', 'analytics'], roles: ['Data Cleaner', 'Enrichment Agent', 'Report Builder', 'Anomaly Detector', 'Dashboard Curator', 'ETL Runner'] },
  { category: 'People', tier: 'bulk', tools: ['email', 'calendar', 'docs'], roles: ['Recruiter Screener', 'Interview Scheduler', 'Onboarding Buddy', 'Policy Q&A', 'Engagement Pulse'] },
  { category: 'Legal', tier: 'reasoning', tools: ['docs', 'search'], roles: ['Contract Reviewer', 'Compliance Checker', 'NDA Drafter', 'Policy Summarizer'] },
  { category: 'Engineering', tier: 'reasoning', tools: ['repo', 'ci', 'docs'], roles: ['Code Reviewer', 'Bug Triager', 'Release Notes Writer', 'On-call Assistant', 'Docs Generator', 'Dependency Updater'] },
  { category: 'Research', tier: 'reasoning', tools: ['search', 'web', 'docs'], roles: ['Market Researcher', 'Competitor Analyst', 'Survey Synthesizer', 'Trend Scout', 'Citation Finder'] },
  { category: 'Product', tier: 'reasoning', tools: ['analytics', 'docs'], roles: ['Feedback Synthesizer', 'Roadmap Drafter', 'Release Planner', 'A/B Analyst', 'Churn Investigator'] },
  { category: 'Voice', tier: 'bulk', tools: ['calls', 'crm'], roles: ['Outbound Caller', 'Appointment Setter', 'Reminder Caller', 'Survey Caller', 'Lead Reactivator'] },
];

const INDUSTRIES = [
  'SaaS', 'Real Estate', 'Healthcare', 'E-commerce', 'Education', 'Fintech', 'Hospitality', 'Automotive',
  'Logistics', 'Insurance', 'Manufacturing', 'Travel', 'Media', 'NGO', 'Legal Services', 'Fitness',
  'Beauty', 'Food & Beverage', 'Telecom', 'Energy',
];

function slug(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

function generateAgents(): AgentTemplate[] {
  const out: AgentTemplate[] = [];
  for (const g of TAXONOMY) {
    for (const role of g.roles) {
      for (const industry of INDUSTRIES) {
        out.push({
          id: `${slug(industry)}-${slug(role)}`,
          name: `${industry} ${role}`,
          category: g.category,
          role,
          industry,
          description: `A ${role} agent tuned for ${industry}: works the ${g.category.toLowerCase()} loop 24/7 using ${g.tools.slice(0, 3).join(', ')}.`,
          tools: g.tools,
          tier: g.tier,
        });
      }
    }
  }
  return out;
}

const DB_ENGINES: DbEngine[] = [
  { id: 'postgres', name: 'PostgreSQL 16', image: 'postgres:16-alpine', port: 5432, env: { POSTGRES_PASSWORD: '' }, scheme: 'postgresql', dataDir: '/var/lib/postgresql/data' },
  { id: 'mysql', name: 'MySQL 8', image: 'mysql:8', port: 3306, env: { MYSQL_ROOT_PASSWORD: '' }, scheme: 'mysql', dataDir: '/var/lib/mysql' },
  { id: 'mariadb', name: 'MariaDB 11', image: 'mariadb:11', port: 3306, env: { MARIADB_ROOT_PASSWORD: '' }, scheme: 'mysql', dataDir: '/var/lib/mysql' },
  { id: 'redis', name: 'Redis 7', image: 'redis:7-alpine', port: 6379, env: {}, scheme: 'redis', dataDir: '/data' },
  { id: 'mongo', name: 'MongoDB 7', image: 'mongo:7', port: 27017, env: { MONGO_INITDB_ROOT_PASSWORD: '' }, scheme: 'mongodb', dataDir: '/data/db' },
  { id: 'clickhouse', name: 'ClickHouse', image: 'clickhouse/clickhouse-server:24-alpine', port: 8123, env: {}, scheme: 'http', dataDir: '/var/lib/clickhouse' },
];

const TLDS: DomainTld[] = [
  { tld: 'com', priceInrYear: 899, popular: true },
  { tld: 'in', priceInrYear: 699, popular: true },
  { tld: 'ai', priceInrYear: 8999, popular: true },
  { tld: 'io', priceInrYear: 3499, popular: true },
  { tld: 'co', priceInrYear: 2299 },
  { tld: 'app', priceInrYear: 1499 },
  { tld: 'dev', priceInrYear: 1399 },
  { tld: 'cloud', priceInrYear: 1799 },
  { tld: 'org', priceInrYear: 999 },
  { tld: 'net', priceInrYear: 1099 },
  { tld: 'tech', priceInrYear: 3999 },
  { tld: 'store', priceInrYear: 4999 },
  { tld: 'shop', priceInrYear: 2999 },
  { tld: 'xyz', priceInrYear: 199 },
];

const HOSTING_PLANS: HostingPlan[] = [
  { id: 'static', name: 'Static Site', runtime: 'static', description: 'HTML/JS/CSS served behind the edge — fastest, cheapest.', defaultImage: 'nginx:alpine', port: 80 },
  { id: 'node', name: 'Node App', runtime: 'node', description: 'A Node.js service (Next/Express/etc.) built and run as a container.', defaultImage: 'node:20-alpine', port: 3000 },
  { id: 'container', name: 'Container', runtime: 'container', description: 'Bring any OCI image; we run + supervise + route it.', port: 8080 },
];

export class Catalog {
  private readonly _agents: AgentTemplate[];
  constructor() {
    // Workforce roles are first-class catalog agents (hire = the same provision path; agentById
    // resolves them) — they just carry the salary/JD/KPI overlay on top.
    this._agents = [...WORKFORCE, ...generateAgents()];
  }

  workforce(): WorkforceRole[] {
    return WORKFORCE;
  }

  workforceById(id: string): WorkforceRole | undefined {
    return WORKFORCE.find((w) => w.id === id);
  }

  agents(opts: { q?: string; category?: string; limit?: number; offset?: number } = {}): {
    total: number;
    items: AgentTemplate[];
    categories: string[];
  } {
    const q = (opts.q ?? '').trim().toLowerCase();
    const cat = opts.category && opts.category !== 'all' ? opts.category : undefined;
    let filtered = this._agents;
    if (cat) filtered = filtered.filter((a) => a.category === cat);
    if (q) {
      filtered = filtered.filter(
        (a) =>
          a.name.toLowerCase().includes(q) ||
          a.role.toLowerCase().includes(q) ||
          a.industry.toLowerCase().includes(q) ||
          a.category.toLowerCase().includes(q),
      );
    }
    const rawOffset = Number(opts.offset);
    const offset = Number.isFinite(rawOffset) ? Math.max(0, Math.trunc(rawOffset)) : 0;
    const rawLimit = Number(opts.limit);
    const limit = Number.isFinite(rawLimit) ? Math.min(200, Math.max(1, Math.trunc(rawLimit))) : 60;
    return {
      total: filtered.length,
      items: filtered.slice(offset, offset + limit),
      categories: this.agentCategories(),
    };
  }

  agentById(id: string): AgentTemplate | undefined {
    return this._agents.find((a) => a.id === id);
  }

  agentCount(): number {
    return this._agents.length;
  }

  agentCategories(): string[] {
    return ['Workforce', ...TAXONOMY.map((t) => t.category)];
  }

  databases(): DbEngine[] {
    return DB_ENGINES;
  }
  databaseById(id: string): DbEngine | undefined {
    return DB_ENGINES.find((d) => d.id === id);
  }
  domainTlds(): DomainTld[] {
    return TLDS;
  }
  hostingPlans(): HostingPlan[] {
    return HOSTING_PLANS;
  }
  hostingPlanById(id: string): HostingPlan | undefined {
    return HOSTING_PLANS.find((h) => h.id === id);
  }
}
