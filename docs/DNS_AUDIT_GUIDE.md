# DNS Audit Guide — Email Deliverability Made Simple

> *Ensure your emails land in the inbox, not the spam folder.*

---

## What is a DNS Audit?

A **DNS audit** checks that your sender domain is properly configured to send email. When you send email from a custom domain (like `yourcompany.com`), the receiving server (Gmail, Outlook, etc.) checks your domain's DNS records to decide if your email is legitimate.

The app runs these checks automatically and gives you a **health score from 0 to 100**. The higher the score, the more likely your emails will reach the inbox.

---

## The Five DNS Checks

### 1. SPF — Sender Policy Framework

**What it does:** SPF is a DNS record that lists which servers are allowed to send email from your domain. Think of it as a guest list for your domain's front door.

**Why it matters:** Without SPF, spammers can forge your domain and send email pretending to be you. Receiving servers will reject or spam-flag your legitimate emails.

**How to set it up:**
1. Log into your domain's DNS management (GoDaddy, Cloudflare, Namecheap, etc.)
2. Add a **TXT record** with:
   - **Host/Name:** `@` or yourdomain.com
   - **Value:** `v=spf1 include:_spf.google.com ~all` (for Google Workspace) — or include your email provider's SPF value

> **Tip:** Use `~all` (soft fail) while testing, then switch to `-all` (hard fail) when everything works.

### 2. DKIM — DomainKeys Identified Mail

**What it does:** DKIM adds a digital signature to every email you send. The receiving server checks this signature against a public key stored in your DNS. If the signature matches, the email is verified as authentic.

**Why it matters:** DKIM is the strongest signal that your email is legitimate. Most major email providers require DKIM for good deliverability.

**How to set it up:**
1. Your email provider (Gmail, Outlook, etc.) generates a DKIM key for you
2. In your domain's DNS, add a **TXT record** with:
   - **Host/Name:** The DKIM selector (e.g., `google._domainkey`)
   - **Value:** The public key from your provider (looks like `v=DKIM1; k=rsa; p=MIGfMA0G...`)

> **Tip:** Each email provider has different DKIM setup steps. Check their documentation for the exact selector and key.

### 3. DMARC — Domain-based Message Authentication, Reporting & Conformance

**What it does:** DMARC tells receiving servers what to do when an email **fails** SPF or DKIM checks. You can instruct them to:
- `none` — Take no action (monitoring only)
- `quarantine` — Send to spam
- `reject` — Block the email entirely

**Why it matters:** DMARC gives you control over how your domain is protected. It also sends you reports about who is sending email from your domain.

**How to set it up:**
1. In your domain's DNS, add a **TXT record** with:
   - **Host/Name:** `_dmarc`
   - **Value:** `v=DMARC1; p=none; rua=mailto:you@yourdomain.com`

> **Tip:** Start with `p=none` to collect reports without affecting delivery. Move to `p=quarantine` once you're confident, and `p=reject` for full protection.

### 4. MX — Mail Exchange

**What it does:** MX records tell the internet where to deliver email sent to your domain. If you use Gmail, the MX record points to Google's mail servers.

**Why it matters:** MX records are required for receiving email. The audit checks that your MX records exist and point to valid mail servers.

**How to set it up:**
1. Most email providers give you MX records when you set up your domain
2. Add them in your DNS with:
   - **Priority:** Lower numbers = higher priority (e.g., 1, 5, 10)
   - **Target:** Your provider's mail server (e.g., `aspmx.l.google.com`)

### 5. rDNS — Reverse DNS (PTR Record)

**What it does:** rDNS is the reverse of a normal DNS lookup — it maps an **IP address** back to a **domain name**. When your email server connects, receiving servers check that the IP address matches your sending domain.

**Why it matters:** Many receiving servers require rDNS to match your sending domain. If it doesn't match, your email may be rejected or flagged.

**How to set it up:**
1. Contact your hosting provider or ISP (they control the rDNS for your IP)
2. Ask them to set the **PTR record** for your sending IP to match your sending domain

> **Tip:** rDNS is often the trickiest to set up because it requires your hosting provider's help.

---

## How the Audit Works in This App

### Running an Audit
1. Go to **Settings > SMTP Senders**
2. Find your sender and click **Audit DNS**
3. The app queries Cloudflare's DNS-over-HTTPS (DoH) service for each check
4. Results appear within seconds — green for pass, amber for warning, red for fail

### Understanding the Score

| Score | Meaning | What to Do |
|-------|---------|------------|
| **80–100** | Excellent — your DNS is well configured | Keep monitoring |
| **50–79** | Good — most checks pass | Fix any failing checks |
| **20–49** | Poor — significant deliverability risk | Prioritize fixing SPF, DKIM, and DMARC |
| **0–19** | Critical — emails likely landing in spam | Set up DNS records immediately |

### Reading the Results

Each check shows:
- ✅ **Pass** — This record is properly configured
- ⚠️ **Warning** — Record exists but may need attention
- ❌ **Fail** — Record is missing or misconfigured

Passed checks are collapsed by default so you can focus on what needs fixing.

---

## Quick Setup by Provider

### Google Workspace / Gmail
| Record | Value |
|--------|-------|
| **SPF** | `v=spf1 include:_spf.google.com ~all` |
| **DKIM** | Generated in Google Admin > Apps > Gmail > Authenticate Email |
| **DMARC** | `v=DMARC1; p=quarantine; rua=mailto:admin@yourdomain.com` |
| **MX** | `aspmx.l.google.com` (and 4 backup records) |

### Microsoft 365 / Outlook
| Record | Value |
|--------|-------|
| **SPF** | `v=spf1 include:spf.protection.outlook.com ~all` |
| **DKIM** | Enabled in Microsoft 365 Admin > Exchange > DKIM |
| **DMARC** | `v=DMARC1; p=quarantine; rua=mailto:admin@yourdomain.com` |
| **MX** | `yourdomain-com.mail.protection.outlook.com` |

---

## Frequently Asked Questions

**Q: Do I need all five checks to pass?**
A: SPF, DKIM, and DMARC are the most important. MX is required for receiving email. rDNS is important but harder to set up — do it if you can.

**Q: How long does it take for DNS changes to work?**
A: DNS propagation can take from 5 minutes to 48 hours, though most updates work within an hour.

**Q: Will the audit fix my DNS for me?**
A: No — the audit only checks your existing DNS records. You need to make changes through your domain provider's control panel. Think of the audit as a health check, not a doctor.

**Q: My audit score is 100 but emails still go to spam. Why?**
A: DNS is one piece of the puzzle. Other factors include email content (spammy words, too many links), sending reputation (new domains start cold), and engagement rates. Check your email content and warm up your domain gradually.

**Q: The app uses Cloudflare for DNS lookups. Is my data safe?**
A: Yes. The app only queries your domain's **public** DNS records — the same information anyone can look up. No sensitive data is sent to Cloudflare.

---

## Troubleshooting

| Problem | Likely Cause | Solution |
|---------|-------------|----------|
| SPF fails | Missing or incorrect SPF record | Add a TXT record starting with `v=spf1` |
| DKIM fails | Public key missing or wrong selector | Check your email provider's DKIM setup guide |
| DMARC fails | No `_dmarc` TXT record | Add `v=DMARC1; p=none` to start |
| MX fails | No MX records for your domain | Add MX records from your email provider |
| rDNS fails | ISP hasn't set PTR record | Contact your hosting provider |
| All checks fail | Domain doesn't exist or DNS is down | Verify your domain is active and DNS is propagated |

---

## Glossary

| Term | Meaning |
|------|---------|
| **DNS** | Domain Name System — the phonebook of the internet |
| **TXT Record** | A DNS record that stores text information (used for SPF, DKIM, DMARC) |
| **Selector** | A unique identifier for your DKIM key (varies by provider) |
| **Propagation** | The time it takes for DNS changes to spread across the internet |
| **DoH** | DNS-over-HTTPS — a secure way to query DNS records |
| **Health Score** | A 0–100 rating of your DNS configuration quality |

---

*This guide is built into the app for quick reference. Click **Learn More** next to any sender's DNS Audit button to open this information directly in the app.*
