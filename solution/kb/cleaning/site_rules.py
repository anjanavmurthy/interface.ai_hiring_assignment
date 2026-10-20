"""Everything specific to this website's template, in one place.

The cleaning and page-type logic elsewhere is generic; the patterns below are what makes it fit dupaco.com.
Each one was confirmed against the snapshots before it was added (exact lines, seen on many pages in all
five downloads), so they remove template noise and never page content.
"""
from __future__ import annotations

import re

# --- R1 teaser sections: "Handpicked for You" / "Recent News" blocks of cards linking to other pages ------
# Articles: '#### [title](url)', a summary and a 'Read More' / 'Keep reading' link per card.
TEASER_CARD_TITLE = re.compile(r"^#### \[.+\]\(https?://[^)\s]*dupaco\.com[^)\s]*\)\s*$")
TEASER_READ_MORE = re.compile(r"^\[(?:Read More|Read more|Keep reading)\]\(")
# Product, calculator and other pages: '[**title**](url)', a short date ('Sep 17, 2026') and a summary per
# card, often followed by one link to more articles ('Read more money tips', 'See all business resources').
# The date tells cards apart from bold feature links, which use the same link style without one.
TEASER_BOLD_TITLE = re.compile(r"^\[\*\*.+\*\*\]\(https?://[^)\s]*dupaco\.com[^)\s]*\)\s*$")
TEASER_SHORT_DATE = re.compile(r"^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{1,2}, \d{4}$")
TEASER_MORE_LINK = re.compile(r"^\[(?:Read|Get|See) (?:more|all)\b[^\]]*\]\(", re.I)

# --- R2 external-link warning modal ---------------------------------------------------------------------
POPUP_LINES = {"✕", "**Heads up! This link leads to a different website.**"}      # "✕" close button
POPUP_PREFIXES = (
    "We only do this when it's helpful for you. But we must inform you that Dupaco isn't responsible",
    "We only do this when it’s helpful for you. But we must inform you that Dupaco isn’t responsible",
)
POPUP_CONTINUE = re.compile(r"^\[Continue\]\([^)]*\)\s*Cancel\s*$")

# --- R5 captcha and chat widget leftovers (exact lines) -------------------------------------------------
WIDGET_LINES = {
    "reCAPTCHA", "Please try again.", "Please select all matching images.", "Please also check the new images.",
    "Please select around the object, or reload if there are none.",
    "Third Party Plugins", "Messenger Launcher", "Messenger",
    "Previous", "Next",                                  # carousel buttons
    "Recaptcha requires verification.", "protected by **reCAPTCHA**", "CAPTCHA", "Verify",
}
# the captcha challenge line: "Select all squares with **boats** If there are none, click skip"
CAPTCHA_CHALLENGE = re.compile(r"^Select all (?:images|squares) with .*click (?:verify|skip)", re.I)
# the visitor's IP address, printed on its own line by the subscription widget (a new one in every download)
VISITOR_IP = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")

# --- R7 form chrome: field labels, submit button, form hints ---------------------------------------------
FORM_LINES = {"Submit"}
FORM_REQUIRED_SUFFIX = re.compile(r"\(Required\)\s*(?:\\\*|\*)?\s*$")
FORM_REQUIRED_QUESTION = re.compile(r"\?\s*\\\*$")      # "What's the best way to contact you?\*"
# Contact fields marked required ("First Name\*", "**Email**\*"), the ones on most forms. Only these exact
# names: other short lines ending in "\*" are often content with a footnote marker ("Document copy fee $1.00\*").
FORM_FIELD = re.compile(r"^(?:\*\*)?(?:First Name|Last Name|Email|Phone Number)(?:\*\*)?\\\*$", re.I)
FORM_PREFIXES = (
    "Hint: This form uses a connection that may not be secure",
    "We’ll only use your information to offer Dupaco products and services",
    "We'll only use your information to offer Dupaco products and services",
)

# --- R8 listing pages: tag / author / category pages only list other pages --------------------------------
LISTING_URL = re.compile(r"/(?:tag|author|category)/")

# --- page types, from URL patterns (first match wins) -----------------------------------------------------
# Used to label every chunk ("rates", "news", ...) so the answer step can tell official pages from old ones.
PAGE_TYPES = [
    ("rates", re.compile(r"/(?:business-)?rates/?$")),
    ("pdf/download", re.compile(r"/hubfs/|\.pdf$", re.I)),
    ("calculator", re.compile(r"/calculators?/")),
    ("promo/landing", re.compile(r"-lp/?$|/switch-and-earn")),
    ("news", re.compile(r"/newsroom/")),
    ("blog/article", re.compile(r"/learn/|/20\d\d/\d\d/|/business/resources/")),
    ("product", re.compile(r"/(?:personal|business)/")),
    ("other (about, contact, ...)", re.compile(r".")),
]
OFFICIAL_PAGE_TYPES = ("product", "rates")   # listed first when the same text appears on several pages

# --- detailed page types, used by the conflicts stages (first match on the page path wins) ------------------
# A finer list than PAGE_TYPES above, made for the conflict experiments: it separates community, help, legal and
# listing pages, and counts more short paths ("/checking") as product pages. Kept separate so the Q&A labels and
# the conflict results each stay exactly as measured; merging the two lists would be its own, measured change.
# Each entry: (type, what it is, regex on the path without the domain).
DETAILED_PAGE_TYPES = [
    ("rates", "official rate sheets", r"^/(business-)?rates/?$"),
    ("pdf", "downloadable documents", r"^/hubfs/|\.pdf$"),
    ("calculator", "calculators and their index", r"^/(business-)?calculators?(/|$)"),
    ("promo/landing", "campaign and landing pages", r"-lp/?$|^/(switch-and-earn|mortgage-refi|homebuying-guidance|earn-more|"
                                                    r"money-makeover|offer-expired|(21-day-)?sprint-to-savings-challenge)/?$"),
    ("news", "press releases (dated)", r"^/newsroom/."),
    ("article", "blog and resource articles (dated)", r"^/learn/.|^/20\d\d/\d\d/|^/dupacodaily/|^/business/resources/."),
    ("listing", "index pages that list other pages", r"^/$|^/(personal|business|loans|newsroom|learn/blog(/page/\d+)?|"
                                                     r"resources(/[\w-]+)?)/?(\?.*)?$"),
    ("product", "product and service pages", r"^/(personal|business)/|^/(checking|savings-account|savings|personal-loans|"
                                             r"financial-services|shine|brighttrack|membership)(/|$)"),
    ("community", "foundation, grants, scholarships", r"^/(community|foundation|scholarships|hardship-grant|non-profit-grant|"
                                                      r"gift-of-innovation-grant|first-time-homebuyer-grant|kccc[\w-]*)/?$|"
                                                      r"/our-impact"),
    ("legal/forms", "disclosures, privacy, forms, thank-you pages", r"disclosures|privacy|^/(photo-release-form|not-for-sale|"
                                                                   r"subscription-preferences|thankuse)"),
    ("about/contact", "about us, joining, careers, contact", r"^/(about|contact|careers)(/|$)"),
    ("help", "digital banking help and safety", r"^/(connect|online-and-mobile-banking|mobile|manage-account-alerts|"
                                                r"protection|covid-19)(/|$)"),
    ("other", "anything else", r"."),
]

# --- facts (kb/facts): the "About Dupaco" paragraph printed under press releases --------------------------------
# Written when each release was published and never updated, so each copy keeps that day's member, asset, employee,
# branch and county counts (~100 pages in every snapshot). It is read once per distinct wording.
ABOUT_FOOTER = re.compile(r"^(?:\**ABOUT DUPACO COMMUNITY CREDIT UNION\**\s*)?Dupaco Community Credit Union is a "
                          r"not-for-profit", re.I)
# On pages that are read only in part (blog, PDF, calculator, help, legal, listing, other), the paragraphs that may
# state a fact about Dupaco: Dupaco ("we", "our") next to an amount, rate or count, a phone number, or a dupaco.com
# web address. The rest of those pages is general advice, form text or computed examples.
DUPACO_NUMBER = re.compile(r"\b(?:Dupaco|we|our|us)\b[^.]{0,120}(?:\$\d|\d+(?:\.\d+)?\s?%|\b\d{2,}\b)"
                           r"|(?:\$\d|\d+(?:\.\d+)?\s?%)[^.]{0,80}\b(?:Dupaco|we|our)\b", re.I)
PHONE_NUMBER = re.compile(r"\b\d{3}[-.)]\s?\d{3}[-.]\d{4}\b|\bext\.?\s*\d{2,}", re.I)
DUPACO_WEB_ADDRESS = re.compile(r"\b(?:www\.)?dupaco\.com/[\w/-]+", re.I)
# Reading more of those pages (config.FACTS_READ_MORE): also a paragraph with a figure that can go out of date (an
# amount, a rate, a time of day, a date), or in which Dupaco speaks for itself ("we", "our") outside a quotation; a
# quoted member or employee is not the credit union stating a fact. Bare numbers ("step 2", "12 times") are not
# figures here.
CHANGEABLE_FIGURE = re.compile(
    r"\$\s?\d|\d(?:\.\d+)?\s?%|\b\d{1,2}(?::\d{2})?\s?(?:[ap]\.m\.|[ap]m)\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
    r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}\b")
DUPACO_SPEAKS = re.compile(r"\bDUPACO\b|\bDupaco\b|\b[Ww]e\b|\b[Oo]ur\b|\b[Uu]s\b")
QUOTATION = re.compile(r"[“\"][^”\"]*[”\"]|^>.*$", re.M)
