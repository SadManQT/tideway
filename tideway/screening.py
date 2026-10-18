"""Bounded warning heuristics for untrusted business text.

These rules never grant authority, identify fraud, or replace signed approvals.
They deliberately distinguish routine account-verification review from suspected
instruction attacks. Rule coverage is finite; missed paraphrases stay untrusted.
"""
from __future__ import annotations

import html
import re
import unicodedata

# Compose the rules from threat categories rather than individual test phrases.
# These are warning heuristics; a token or intent can always be paraphrased.
_CONTROL_TERMS = r"(?:polic\w*|limits?|approvals?|security|check(?:s|ers?)?|consent|reviewers?|signatures?|authori[sz]ation|pin|passcode|password|otp|co-?signers?|human\s+signers?)"
_AUTHORITY_TERMS = r"(?:authori[sz]ation|consent|approvals?|signatures?|reviewers?|signers?)"
_FINANCIAL_TARGET = r"(?:payment|invoice|funds|money|beneficiary|settlement|payout|remittance|bank|account|destination|disbursement)"
_SENSITIVE_DATA = r"(?:customer\s+(?:records?|ledger|database|data)|payroll\s+(?:ledger|records?|data)|banking\s+credentials?|credentials?|secrets?|tokens?|private\s+keys?|database|all\s+(?:invoices|records|accounts))"
_EXTERNAL_DESTINATION = r"(?:https?://|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b(?:there|outside|external|endpoint|server|private\s+(?:mailbox|inbox)|my\s+(?:inbox|mailbox|email))\b)"

INJECTION_PATTERNS = (
    ("instruction_override", re.compile(r"\b(ignore|disregard|forget)\b.{0,50}\b(instructions?|rules?|prompts?|polic\w*|restrictions?)\b", re.I)),
    ("control_bypass", re.compile(rf"\b(?:override|bypass|disable|skip|omit|waive|circumvent|suspend|eliminate|suppress)\b.{{0,60}}\b{_CONTROL_TERMS}\b", re.I)),
    # Negating a control requirement removes a safeguard. This differs from
    # negating "bypass", which preserves that safeguard. Match the whole
    # removal request so local negation suppression does not invert it again.
    ("control_bypass", re.compile(rf"\b(?:do\s+not|don't|need\s+not|stop|cease)\s+(?:require|requiring|enforce|enforcing|check|checking|request|requesting|ask\s+for|asking\s+for)\b.{{0,55}}\b{_CONTROL_TERMS}\b", re.I)),
    ("control_bypass", re.compile(rf"\b{_CONTROL_TERMS}\b[^.;!?]{{0,65}}\b(?:turn|switch)\b.{{0,25}}\boff\b", re.I)),
    ("control_bypass", re.compile(r"\b(?:without\s+(?:asking\s+)?|no\s+(?:further\s+)?|not\s+require\s+)(?:the\s+|either\s+|human\s+|owner'?s?\s+|any\s+|both\s+){0,3}(?:approv\w*|consent|authorization|callback|review\w*)\b", re.I)),
    ("forged_authority", re.compile(r"\b(?:treat|accept|regard|use)\b.{0,35}\b(?:this\s+(?:note|message)|text|invoice)\b.{0,35}\b(?:authori[sz]ation|consent|approval)\b|\b(?:mark|set)\b.{0,45}\b(?:mandates?|approvals?|payments?)\b.{0,35}\b(?:accepted|approved|signed|authorized)\b", re.I)),
    ("forged_authority", re.compile(rf"\b(?:treat|accept|regard|use|count|consider)\b.{{0,80}}\b(?:as|equivalent|in\s+place\s+of|substitute)\b.{{0,60}}\b{_AUTHORITY_TERMS}\b|\b(?:record|mark|set|consider)\b.{{0,65}}\b(?:mandates?|approvals?|payments?|transfers?)\b.{{0,45}}\b(?:accepted|approved|signed|authori[sz]ed|complete|completed|satisfied)\b", re.I)),
    ("forged_authority", re.compile(rf"\b(?:treat|accept|regard|use|count|consider)\b.{{0,45}}\b(?:chat|message|email|note|text|invoice|stamp|attachment)\b.{{0,55}}\b{_AUTHORITY_TERMS}\b|\b(?:pretend|assume|fabricate|falsify|invent)\b.{{0,60}}\b{_CONTROL_TERMS}\b.{{0,35}}\b(?:passed|complete|completed|done|satisfied|cleared|obtained|granted)\b", re.I)),
    ("control_bypass", re.compile(rf"\b(?:no|without)\s+(?:further\s+|human\s+|owner\s+|manual\s+|additional\s+){{0,3}}{_AUTHORITY_TERMS}\b.{{0,30}}\b(?:needed|required|necessary)\b|\b{_AUTHORITY_TERMS}\b.{{0,20}}\b(?:is|are)\s+(?:unnecessary|optional)\b", re.I)),
    ("payment_redirect", re.compile(r"\b(?:redirect|reroute|divert)\b.{0,60}\b(?:payment|invoice|funds|money|beneficiary|settlement)\b|\b(?:payment|invoice|funds|money)\b.{0,35}\b(?:redirect|reroute|divert)\b", re.I)),
    ("payment_redirect", re.compile(rf"\b(?:replace|substitute|swap|switch|change|amend|route)\b.{{0,65}}\b{_FINANCIAL_TARGET}\b.{{0,65}}\b(?:to|with|for|instead|rather\s+than)\b.{{0,65}}\b(?:account|wallet|beneficiary|bank|coordinates|destination|attachment|below|provide|listed)\b", re.I)),
    ("payment_redirect", re.compile(r"\b(?:use|pay|send|route|select)\b.{0,55}\b(?:wallet|account|beneficiary|destination)\b.{0,60}\b(?:instead\s+of|rather\s+than|in\s+place\s+of)\b.{0,60}\b(?:registered|recorded|verified|established|existing|usual)\b", re.I)),
    ("data_exfiltration", re.compile(rf"\b(?:upload|export|post|transmit|send|copy|forward|fetch|email|mail)\b.{{0,100}}\b{_SENSITIVE_DATA}\b.{{0,100}}{_EXTERNAL_DESTINATION}|\b(?:fetch|visit|open)\b.{{0,100}}https?://.{{0,100}}\b{_SENSITIVE_DATA}\b", re.I)),
    ("concealed_action", re.compile(r"\b(?:hide|conceal|suppress)\b.{0,55}\b(?:payments?|transfers?|disbursements?|execution|owner|user|reviewers?)\b|\b(?:do\s+not|don't|never)\s+(?:show|tell|notify|inform|alert)\b.{0,65}\b(?:owner|user|reviewers?|approvers?)\b.{0,100}\b(?:approve|pay|payment|transfer|transmit|disbursement|execute)\b|\b(?:approve|execute|transmit|pay|release)\b.{0,65}\b(?:silently|secretly|quietly|in\s+secret)\b", re.I)),
    ("audit_tampering", re.compile(r"\b(?:delete|erase|clear|remove|purge|disable|rewrite)\b.{0,45}\b(?:audit\s+(?:trail|logs?|records?)|execution\s+logs?|transaction\s+logs?)\b", re.I)),
    ("action_command", re.compile(r"\b(?:wire|transfer|send|pay|release)\b.{0,60}\b(?:my|attacker|unverified)\s+(?:account|wallet)\b|\b(?:wire|transfer|send|pay|release)\b.{0,35}\b(?:all|full|entire)\s+(?:funds|balance|money)\b", re.I)),
    ("payment_detail_change", re.compile(r"\b(new|updated|changed|different)\b.{0,20}\b(bank\s+(?:details|account|coordinates|beneficiary)|account|iban|swift|bic|sort code|routing|wallet|paypal|wise|payoneer|revolut|alipay|wechat ?pay|upi|paynow|duitnow|promptpay|gcash|m-?pesa|bkash|nagad|pix)\b", re.I)),
    ("payment_detail_change", re.compile(r"\b(?:bank\s+details|account|iban|wallet|beneficiary)\b.{0,20}\b(?:changed|updated|replaced|different)\b", re.I)),
    ("hidden_markup", re.compile(r"<\s*/?\s*(script|system|instructions?|iframe)\b|\{\{\s*(?:tool|system|execute|instructions?)\s*:", re.I)),
    # The same signals in other languages owners and counterparties actually write in.
    ("instruction_override", re.compile(r"(忽略|无视|忘记|不要理会).{0,12}(指令|指示|说明|规则|提示|之前|以上)"
                                        r"|\b(ignora|olvida|ignorez|oubliez|abaikan|lupakan)\b.{0,40}\b(instruc|regla|r[eè]gle|consigne|aturan|perintah|anterior|pr[eé]c[eé]dent|sebelum)"
                                        r"|\b(ignore|bhool)\b.{0,20}\b(karo|kar do|koro|kore dao)\b"
                                        r"|(تجاهل|انس).{0,20}(التعليمات|القواعد)|(আগের|পূর্বের).{0,20}(নির্দেশ).{0,20}(উপেক্ষা|ভুলে)"
                                        r"|(पिछले|पहले).{0,20}(निर्देश).{0,20}(अनदेखा|भूल)", re.I)),
    ("role_marker", re.compile(r"(^|\s)(系统|助手|sistema|syst[eè]me|asisten|النظام)\s*[:：]", re.I)),
    ("action_command", re.compile(r"(立即|马上|立刻).{0,12}(转账|付款|支付|批准|汇款)|(转账|付款|汇款).{0,20}(新账户|新账号)"
                                  r"|\b(transfiere|paga|aprueba|transf[eé]rez|payez|approuvez|transfer|bayar|setujui)\b.{0,60}\b(ahora|inmediatamente|maintenant|imm[eé]diatement|sekarang|segera)\b", re.I)),
    ("payment_detail_change", re.compile(r"(新|更改|变更|更新).{0,6}(银行|账户|账号|收款码|支付宝|微信)"
                                         r"|\b(rekening baru|akun baru|cuenta nueva|nouveau compte|nouveau rib)\b"
                                         r"|\b(nueva|nuevo|cambiamos|nouveau|nouvelle|naya)\b.{0,20}\b(cuenta|banco|compte|banque|rekening|account)\b", re.I)),
    ("control_bypass", re.compile(r"(绕过|跳过|关闭).{0,8}(审批|限制|安全|检查)|\b(omite|salta|contourne|lewati)\b.{0,30}\b(aprobaci|approbation|persetujuan|l[ií]mite|limit)", re.I)),
)

# Compositions are deliberately bounded to one clause and require both a
# dangerous operation and its target. These are language rules, not lists of
# evaluation messages. Account changes alone still request verification only.
INJECTION_PATTERNS += (
    ("payment_detail_change", re.compile(r"\b(?:update|change|amend|replace|revise)\b.{0,24}\b(?:bank\s+(?:details|account)|beneficiary(?:\s+(?:details|account))?|iban|swift|routing\s+(?:number|details)|wallet\s+address)\b", re.I)),
    ("payment_detail_change", re.compile(r"(?:নতুন|পরিবর্তিত|বদলানো).{0,20}(?:ব্যাংক|অ্যাকাউন্ট|হিসাব|ওয়ালেট|ওয়ালেট)|(?:नया|नए|बदला|नवीन).{0,15}(?:बैंक|खाता|वॉलेट)|(?:جديد|تحديث).{0,15}(?:حساب|البنك)|(?:حساب|البنك).{0,15}جديد")),
    ("instruction_override", re.compile(r"\b(?:set|put|leave|cast)\b.{0,35}\b(?:instructions?|rules?|polic\w*|safeguards?)\b.{0,25}\b(?:aside|behind|away)\b|\b(?:supersede|overrule|replace)\b.{0,45}\b(?:system|developer|previous|earlier|original)\b.{0,20}\b(?:instructions?|rules?|prompts?|polic\w*)\b", re.I)),
    ("control_bypass", re.compile(rf"\b(?:must\s+not|should\s+not|never)\s+(?:require|enforce|request|check|ask\s+for)\b.{{0,55}}\b{_CONTROL_TERMS}\b|\b(?:get\s+around|work\s+around|avoid|evade|remove|drop|lift)\b.{{0,45}}\b{_CONTROL_TERMS}\b|\b{_CONTROL_TERMS}\b.{{0,30}}\b(?:does\s+not|doesn't|will\s+not|won't)\s+apply\b", re.I)),
    ("forged_authority", re.compile(rf"\b(?:impersonate|pose\s+as|act\s+as|pretend\s+to\s+be)\b.{{0,40}}\b(?:owner|administrator|admin|reviewer|approver|signer|bank|auditor)\b|\b(?:satisfy|satisfies|replace|replaces|substitute\s+for)\b.{{0,35}}\b(?:required|owner|human|second|both)\b.{{0,25}}\b{_AUTHORITY_TERMS}\b|\b(?:forge|fake|fabricate|falsify)\b.{{0,50}}\b(?:mandates?|approvals?|consent|signatures?|receipts?|read.?backs?)\b", re.I)),
    ("data_exfiltration", re.compile(rf"\b(?:leak|dump|disclose|share|deliver|publish|attach)\b.{{0,80}}\b{_SENSITIVE_DATA}\b.{{0,90}}{_EXTERNAL_DESTINATION}|\b(?:api[ _-]?keys?|access[ _-]?tokens?|session[ _-]?(?:cookies?|tokens?)|passwords?)\b.{{0,65}}\b(?:send|forward|upload|copy|post)\b.{{0,80}}{_EXTERNAL_DESTINATION}", re.I)),
    ("concealed_action", re.compile(r"\b(?:keep|leave)\b.{0,35}\b(?:owner|reviewers?|approvers?|user)\b.{0,20}\b(?:uninformed|unaware|out\s+of\s+(?:the\s+)?loop)\b|\b(?:omit|remove|suppress|disable|silence)\b.{0,35}\b(?:notifications?|alerts?|approval\s+emails?)\b.{0,45}\b(?:pay|payment|transfer|execute|settlement)\b", re.I)),
    ("audit_tampering", re.compile(r"\b(?:hide|conceal|alter|modify|falsify|truncate|wipe)\b.{0,45}\b(?:audit\s+(?:trail|logs?|records?)|execution\s+logs?|transaction\s+logs?|approval\s+(?:history|records?))\b", re.I)),
    ("encoded_instruction", re.compile(r"\b(?:decode|decrypt|base64|rot13)\b.{0,70}\b(?:execute|obey|follow|run|instructions?|commands?)\b|\b(?:execute|obey|follow|run)\b.{0,50}\b(?:decoded|decrypted|base64|rot13)\b", re.I)),
    ("control_bypass", re.compile(r"(?:অনুমোদন|অনুমতি|স্বাক্ষর|নিরাপত্তা|পিন|যাচাই).{0,30}(?:ছাড়া|ছাড়া|লাগবে না|প্রয়োজন নেই|প্রয়োজন নেই|বাদ দাও|বাদ দিন|এড়িয়ে|এড়িয়ে)|(?:বাদ|এড়িয়ে|এড়িয়ে|বাইপাস).{0,20}(?:অনুমোদন|অনুমতি|স্বাক্ষর|পিন|নিরাপত্তা|যাচাই)")),
    ("forged_authority", re.compile(r"(?:বার্তা|মেসেজ|চ্যাট|ইমেইল|নোট).{0,35}(?:অনুমোদন|সম্মতি|স্বাক্ষর).{0,25}(?:ধরো|ধরুন|গণ্য|বিবেচনা)|(?:মালিক|প্রশাসক|অনুমোদনকারী).{0,20}(?:সেজে|পরিচয় দিয়ে|পরিচয় দিয়ে)")),
    ("payment_redirect", re.compile(r"(?:নিবন্ধিত|যাচাইকৃত|পুরোনো|আসল).{0,20}(?:অ্যাকাউন্ট|হিসাব|ওয়ালেট|ওয়ালেট).{0,25}(?:বদলে|পরিবর্তে).{0,35}(?:অ্যাকাউন্ট|হিসাব|ওয়ালেট|ওয়ালেট)|(?:টাকা|পেমেন্ট|তহবিল).{0,25}(?:ঘুরিয়ে|ঘুরিয়ে|অন্যত্র).{0,20}(?:পাঠাও|পাঠান|সরাও)")),
    ("concealed_action", re.compile(r"(?:মালিক|পর্যালোচক|অনুমোদনকারী).{0,25}(?:জানাবে না|জানাবেন না|না জানিয়ে|না জানিয়ে)|(?:গোপনে|চুপিচুপি).{0,30}(?:পাঠাও|পাঠান|ট্রান্সফার|পেমেন্ট|অনুমোদন)")),
    ("control_bypass", re.compile(r"(?:अनुमति|अनुमोदन|हस्ताक्षर|सुरक्षा|पिन|जाँच|जांच).{0,25}(?:बिना|ज़रूरी नहीं|जरूरी नहीं|हटा दो|छोड़ दो)|(?:बिना|हटा|छोड़|छोड़).{0,20}(?:अनुमति|अनुमोदन|हस्ताक्षर|सुरक्षा|पिन|जाँच|जांच)")),
    ("control_bypass", re.compile(r"(?:无需|不必|不要(?!\s*(?:绕过|跳过|关闭|取消|免除|省略|伪造))|取消|免除|省略).{0,12}(?:批准|审批|签名|验证|授权|安全检查)|(?:批准|审批|签名|授权).{0,12}(?:不需要|无需|不必要)")),
    ("forged_authority", re.compile(r"(?:把|将|视为|当作).{0,20}(?:消息|邮件|聊天|便条).{0,20}(?:授权|批准|签名)|(?:伪造|假装).{0,20}(?:授权|批准|签名|审核)")),
    ("payment_redirect", re.compile(r"(?:替换|更换|改用|改成).{0,15}(?:我的|私人|未验证).{0,10}(?:收款人|账户|账号|钱包)|(?:已验证|登记|原有).{0,15}(?:账户|账号).{0,20}(?:替换|换成|改用|改成|代替)|(?:不要|不用).{0,10}(?:已验证|登记|原有).{0,10}(?:账户|账号)")),
    ("data_exfiltration", re.compile(r"(?:上传|发送|导出|复制|转发).{0,25}(?:客户数据|客户记录|工资记录|密码|密钥|令牌|所有发票).{0,35}(?:https?://|邮箱|外部|服务器)")),
    ("data_exfiltration", re.compile(rf"(?:ग्राहक\S*|कर्मचार\S*).{{0,65}}(?:नाम|पते|मोबाइल|फोन|वेतन|सूची).{{0,100}}{_EXTERNAL_DESTINATION}.{{0,30}}(?:भेज|निर्यात|अपलोड)|(?:भेज|निर्यात|अपलोड).{{0,50}}(?:ग्राहक\S*|कर्मचार\S*).{{0,100}}{_EXTERNAL_DESTINATION}", re.I)),
    ("control_bypass", re.compile(r"\b(?:sin|sans|tanpa)\s+(?:la\s+|les\s+|aucune\s+)?(?:aprobaci[oó]n|autorizaci[oó]n|approbation|autorisation|persetujuan|izin)\b|\b(?:desactiva|elimina|suprime|d[eé]sactivez|supprimez|nonaktifkan|hapus)\b.{0,35}\b(?:controles?|validaci[oó]n|approbation|v[eé]rification|persetujuan|keamanan)\b", re.I)),
    ("forged_authority", re.compile(r"\b(?:considera|considere|consid[eé]rez|anggap|perlakukan)\b.{0,40}\b(?:mensaje|correo|message|courriel|pesan|email)\b.{0,40}\b(?:firma|autorizaci[oó]n|consentimiento|signature|autorisation|persetujuan|tanda\s+tangan)\b", re.I)),
    ("control_bypass", re.compile(r"(?:تجاوز|تخطى|تخطّي|عطّل|عطل|إلغاء|الغاء).{0,25}(?:الموافقة|موافقة|التفويض|التحقق|الأمان|الامان)|(?:بدون|دون).{0,15}(?:موافقة|تفويض|توقيع)")),
)

# Flags signal review, not malicious intent. Payment-detail changes remain
# quarantined even when a supplier's request is legitimate. A receipt URL or
# an ordinary role-like heading alone is not an instruction attack.
PAYMENT_REVIEW_FLAGS = frozenset({"payment_detail_change"})
_ROLE_MARKER = re.compile(r"(^|\s)(system|assistant|developer|tool|系统|助手|sistema|syst[eè]me|asisten|النظام)\s*[:：]", re.I)
_ACTION_WORD = re.compile(r"\b(?:approve|execute|transfer|wire|send|pay|release)\b", re.I)
_LINK = re.compile(r"https?://|www\.", re.I)
_ROLE_MARKER = re.compile(_ROLE_MARKER.pattern + r"|\[(?:/?INST|system|assistant|developer|tool)\]|<\|(?:system|assistant|developer|tool)\|>", re.I)
_NEGATION = re.compile(r"\b(?:never|must\s+not|do\s+not|don't|should\s+not|cannot|can't|not\s+to|not|avoid|forbid|prohibit)\s+(?:\w+\s+){0,2}$", re.I)
_CLAUSE_BOUNDARY = re.compile(r"[;!?\n。！？；।]+|\.(?=\s|$)|\b(?:but|however|instead(?!\s+of\b)|yet|also|nevertheless|pero|mais|pourtant|tetapi|namun)\b|কিন্তু|তবে|但是|然而|لكن", re.I)
_CONFUSABLES = str.maketrans({
    "а": "a", "А": "A", "е": "e", "Е": "E", "о": "o", "О": "O",
    "р": "p", "Р": "P", "с": "c", "С": "C", "х": "x", "Х": "X",
    "у": "y", "У": "Y", "і": "i", "І": "I", "ј": "j", "Ј": "J",
})
_OBFUSCATED_WORDS = (
    "ignore", "disregard", "bypass", "disable", "approval", "security", "password",
    "consent", "authorize", "authorise", "transfer", "execute", "credentials", "secret",
    "system", "developer", "instructions", "override", "audit", "delete", "export",
)
_SPELLED_WORD = re.compile(
    r"(?<!\w)(?:" + "|".join(r"[\s._-]*".join(word) for word in _OBFUSCATED_WORDS) + r")(?!\w)", re.I)
_LEET_WORDS = frozenset(_OBFUSCATED_WORDS) | {"pin", "rules", "policy", "account", "funds", "send"}
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t"})
_QUOTED = re.compile(r'"[^"\n]{1,1000}"|“[^”\n]{1,1000}”|«[^»\n]{1,1000}»|「[^」\n]{1,1000}」|‘[^’\n]{1,1000}’|(?<!\w)\'[^\'\n]{1,1000}\'(?!\w)')
_APPLY_QUOTED = re.compile(r"\b(?:obey|follow|apply|execute|carry\s+out|act\s+on|comply\s+with)\b.{0,55}\b(?:quote|quoted|above|below|attached|those|these|that|instructions?|directions?|commands?)\b"
                           r"|(?:执行|遵循|照做).{0,18}(?:引号|引用|上述|指令)|(?:উদ্ধৃত|উপরের|সেই).{0,25}(?:অনুসরণ|পালন|কার্যকর)"
                           r"|\b(?:sigue|aplica|suivez|appliquez|ikuti)\b.{0,35}\b(?:cita|citation|cit[eé]|kutipan)\b"
                           r"|(?:نفذ|اتبع).{0,20}(?:اقتباس|المقتبس)", re.I)


def _normalise(value):
    """Fold common display obfuscation for matching, without modifying records.

    Do not decode arbitrary base64, URLs or executable payloads. Explicit
    decode-and-obey requests have their own warning; there is no execution.
    """
    value = html.unescape(unicodedata.normalize("NFKC", value))
    value = "".join(c for c in value if unicodedata.category(c) != "Cf")
    value = re.sub(r"(?<=\w)’(?=\w)", "'", value).replace("`", "'")

    def fold_word(match):
        original = match.group()
        folded = original.translate(_CONFUSABLES)
        # Only mixed Latin tokens are folded, preserving ordinary Cyrillic.
        if re.search(r"[A-Za-z]", original):
            original = folded
        candidate = original.casefold().translate(_LEET)
        return candidate if candidate in _LEET_WORDS else original

    value = re.sub(r"[\w]+", fold_word, value)
    return _SPELLED_WORD.sub(lambda match: re.sub(r"[\s._-]", "", match.group()), value)


def _mask_reported_quotes(value):
    """Exclude explicitly reported/rejected examples, never bare commands.

    Reporting context is a usability heuristic. It cannot make quoted text
    executable or safe, and an instruction to apply the quote is still scanned.
    """
    if _APPLY_QUOTED.search(value):
        return value
    pieces = list(value)
    for match in _QUOTED.finditer(value):
        prefix = value[max(0, match.start() - 100):match.start()]
        suffix = value[match.end():match.end() + 100]
        reported = re.search(r"\b(?:example\s+(?:of|text)|training\s+example|quoted\s+(?:example|text)|(?:rejected|blocked|flagged|reported|detected|received)\s+(?:(?:an?|the|this|that|a\s+suspicious)\s+)?(?:message|request|instruction|email|text)?|(?:message|email|report)\s+(?:said|reads?|states?|contained)|(?:supplier|sender|caller)\s+(?:wrote|said))\s*[:,-]?\s*$", prefix, re.I)
        training = re.search(r"(?:training\s+(?:example|handout)|inactive\s+example|培训.{0,12}(?:示例|例子)|示例坏请求|প্রশিক্ষণ.{0,25}উদাহরণ|অনুশীলন.{0,20}|उदाहरण|प्रशिक्षण|مثال.{0,20}تدريب|تمرين|(?:exemple|ejemplo|exerc[ií]cio).{0,30}(?:formation|formaci[oó]n|capacita|p[eé]dagog)|fiche\s+p[eé]dagogique).{0,25}$", prefix, re.I)
        rejected = re.match(r"\s*(?:is|was|would\s+be|must\s+be|should\s+be)\s+(?:an?\s+)?(?:attack|injection|prohibited|forbidden|unsafe|rejected|blocked|disallowed)\b", suffix, re.I)
        if reported or rejected or training:
            pieces[match.start():match.end()] = " " * (match.end() - match.start())
    return "".join(pieces)


def _mask_rejected_questions(value):
    """An immediately rejected question is not an active bypass request.

    Only mask that question; subsequent instructions remain independently
    scanned. The rejection must be a complete sentence, not 'No problem'.
    """
    pattern = re.compile(r"(?:^|(?<=[.!?\n]))[^.!?\n]{0,300}\?\s*(?:no|it\s+does\s+not|we\s+cannot)[.!](?=\s|$)", re.I)
    def replace(match):
        question = match.group().split("?", 1)[0]
        if re.search(r"\b(?:can|could|may|should)\b|\basking\s+whether\b", question, re.I):
            return " " * len(match.group())
        return match.group()
    value = pattern.sub(replace, value)
    indirect = re.compile(r"(?:^|(?<=[.!?\n]))[^.!?\n]{0,120}\basking\s+whether\b[^.!?\n]{1,200}[.?]\s*(?:no|it\s+does\s+not|we\s+cannot)[.!](?=\s|$)", re.I)
    return indirect.sub(lambda match: " " * len(match.group()), value)


def _negated_at(value, start, end):
    """Suppress locally negated prohibitions, not an entire mixed message."""
    prefix = value[max(0, start - 90):start]
    suffix = value[end:end + 75]
    if _NEGATION.search(prefix):
        return True
    if re.search(r"\b(?:reject|block|report|flag|detect|prohibit)\b.{0,40}\b(?:requests?|attempts?|instructions?)\s+to\s*$", prefix, re.I):
        return True
    if re.match(r"\s*(?:is|are|was|would\s+be|must\s+be)\s+(?:strictly\s+)?(?:prohibited|forbidden|blocked|disallowed|unsafe|unacceptable)\b", suffix, re.I):
        return True
    if re.search(r"(?:不要|禁止|不得|切勿)\s*$", prefix):
        return True
    if re.match(r".{0,30}?(?:করবেন না|করো না|করবেননা|ছাড়বেন না|ছাড়বেন না|পাঠাবেন না|দেবেন না|मत करो|न करें)(?:\s|$)", suffix):
        return True
    if re.match(r"(?:sin\b|sans\b|tanpa\b|بدون|دون)", value[start:], re.I):
        if re.search(r"\b(?:no\s+(?:pagues|pagar|transfieras|env[ií]es)|ne\b.{0,25}\b(?:pas|jamais)|jangan\s+(?:bayar|transfer|kirim))\b.{0,20}$|لا\s+(?:ترسل|تدفع|تحول).{0,20}$", prefix, re.I):
            return True
    if re.match(r"without\b", value[start:], re.I):
        # "No payment is allowed without approval" is a prohibition. Limit
        # this exemption to that clause and that match: a later bypass,
        # silent-action, or authority-forging request is scanned separately.
        clause = re.split(r"[.;!?\n]", prefix)[-1]
        return bool(re.search(r"\bno\s+(?:payments?|transfers?|funds?|money|disbursements?)\b(?:\s+(?:is|are))?(?:\s+(?:allowed|permitted|executed|released|sent))?\s*$", clause, re.I)
                    or re.search(r"\b(?:never|do\s+not|must\s+not)\s+(?:pay|release|transfer|send|execute)\b.{0,45}$", clause, re.I))
    return False


def scan_text(*values) -> list[str]:
    """Contextual warning signals; never a source of action authority.

    ``payment_detail_change`` requests independent account verification and
    must not be presented as a positive injection/fraud classification.
    Undetected text remains untrusted: permissions and approvals do not rely
    on these rules. Limited negation handling does not interpret prose fully.
    """
    flags = []
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        value = _normalise(value)
        scanned = _mask_rejected_questions(_mask_reported_quotes(value))
        local = []
        for clause in _CLAUSE_BOUNDARY.split(scanned):
            for name, pattern in INJECTION_PATTERNS:
                if name == "role_marker":
                    continue  # Contextual gating below also covers multilingual headings.
                if any(not _negated_at(clause, match.start(), match.end()) for match in pattern.finditer(clause)):
                    if name not in local:
                        local.append(name)
        attack = any(name not in PAYMENT_REVIEW_FLAGS for name in local)
        if attack and _ROLE_MARKER.search(value):
            local.append("role_marker")
        if attack and _ACTION_WORD.search(value) and "action_command" not in local:
            local.append("action_command")
        if attack and _LINK.search(value):
            local.append("external_link")
        flags.extend(name for name in local if name not in flags)
    return flags


