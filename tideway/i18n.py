"""Replies in the owner's own language.

The assistant answers in English, Chinese, Spanish, French, Portuguese or Indonesian/Malay,
whichever the question was written in (Hinglish and Banglish questions get English, the language
their speakers read on business apps).  Every sentence is a template filled with numbers from
Tideway's own tools, so translation can never change a figure.  Amounts keep ISO 4217 codes.
"""
from __future__ import annotations

import re
from datetime import date

from .domain import money_text

LANGUAGES = ("en", "zh", "es", "fr", "pt", "id")

_WORDS = {
    "en": "the is are am my me what how can i to of for do does will show who which why if this a an and with on late days "
          "pay pays find make give should it our we you your salaries payroll customers risk risky cash forecast worst case "
          "remind everyone owes approve transfer wire money now write poem tell joke book flight weather prepare documents "
          "loan bank credit terms safe chances short month never spend expense happens suppose usually slowest chase "
          "as possible most more less than care about keep out contact exclude skip minimise minimize biggest blocked any "
          "fraud alerts suspicious check security did change changed details hurt depend too much one fails",
    "es": "el la los las un una de del y si en por para con sin qué cómo cuánto cuál puedo mi me te le es está este esta "
          "ahora nunca hazme págale aprueba cuéntame prepara muéstrame recuerda recuérdale sueldos nómina riesgo caja días "
          "tarde clientes factura crédito plan rescate descuento máximo préstamo documentos hola gracias gasto máquina mes "
          "pasa paga pagan suele chiste peor escenario alcanza arriesgado previsión deben",
    "pt": "o os as um uma de do da dos das e se em por para com sem que qual quais como quem posso consigo meu minha é está "
          "este esta agora nunca faça pague aprove cobre mostre prepare salários folha risco caixa dias atraso atrasados "
          "clientes plano desconto máximo empréstimo documentos olá obrigado obrigada eu gastar pior cenário vender prazo "
          "costuma pagar ganhou jogo todos previsão garantida envolver tem algum alerta bloqueadas dependo demais",
    "fr": "le la les un une de des du et si en pour avec sans que quel quels quelle comment combien pourquoi je moi mon ma "
          "mes est ce cette maintenant jamais propose propose-moi paie payez approuve relance montre montre-moi prépare "
          "salaires risque trésorerie jours retard clients plan sauvetage remise maximale prêt dossier bancaire bonjour merci "
          "ne pas d'habitude dépense scénario pire puis-je accorder couverte y a-t-il alertes fraude bloquées dépends",
    "id": "yang dan di ke dari ini itu saya kami apa bagaimana kenapa berapa bisa tidak sudah akan untuk dengan tanpa kalau "
          "jika sekarang bayar gaji karyawan bulan risiko kas hari telat pelanggan rencana penyelamatan diskon maksimal "
          "pinjaman dokumen bank siapkan tunjukkan ingatkan setujui rencananya pesankan tiket pesawat halo terima kasih "
          "transfer aman kredit tempo skenario terburuknya proyeksi arus buatkan biasanya tepat waktu mesin baru keluar",
}
# Banglish and Hinglish speakers read business apps in English, so these count toward English.
_WORDS["en"] += (" ekta banao bad dao ke er beshi na jhuki kom hok keno ei baki diner jonno dibo pathao kon der taka dey jodi "
                 "pore khoroch korle dite parbo beton obostha ki hobe koto shomoymoto kagoj shobaike reminder ek ko mat poochho "
                 "se zyada nahi yeh kyun ka maal din udhaar du kya hai kitna agar kare to bhejo abhi karta pe hoga kharch karu "
                 "paisa sab kaun chahiye kam salary staff customer customers plan e")
_WORDS["es"] += " que pague retraso"
_WORDS["pt"] += " atrasado atrasada"
_WORDS["id"] += " terlambat"
_WORDS = {lang: set(words.split()) for lang, words in _WORDS.items()}
_MARKS = {"es": "ñ¿¡", "pt": "ãõ", "fr": "èàùâîûœ"}


def detect(text):
    """The reply language for a question: Chinese characters, else the language whose common words it uses most."""
    text = str(text)
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    tokens = re.findall(r"[\w'-]+", text.casefold())
    scores = {lang: sum(token in words for token in tokens) for lang, words in _WORDS.items()}
    for lang, marks in _MARKS.items():
        scores[lang] += 2 * any(mark in text.casefold() for mark in marks)
    best = max(scores.values())
    if best == 0 or scores["en"] == best:
        return "en"
    return max((lang for lang in scores if lang != "en"), key=lambda lang: scores[lang])


_MONTHS = {
    "en": "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec", "es": "ene feb mar abr may jun jul ago sep oct nov dic",
    "fr": "janv. févr. mars avr. mai juin juil. août sept. oct. nov. déc.",
    "pt": "jan fev mar abr mai jun jul ago set out nov dez", "id": "Jan Feb Mar Apr Mei Jun Jul Agu Sep Okt Nov Des"}


def day(lang, value):
    """'2026-10-31' in the reader's style: 31 Oct, 31 oct., 10月31日..."""
    if not value:
        return "—"
    parsed = date.fromisoformat(str(value)[:10])
    if lang == "zh":
        return f"{parsed.month}月{parsed.day}日"
    return f"{parsed.day} {_MONTHS.get(lang, _MONTHS['en']).split()[parsed.month - 1]}"


M = {
    "hello": {"en": "Hi {name}! ", "zh": "{name}，你好！", "es": "¡Hola, {name}! ", "fr": "Bonjour {name} ! ",
              "pt": "Olá, {name}! ", "id": "Halo {name}! "},
    "hello_anon": {"en": "Hi! ", "zh": "你好！", "es": "¡Hola! ", "fr": "Bonjour ! ", "pt": "Olá! ", "id": "Halo! "},
    "weather": {"en": {"storm": "Storm", "unsettled": "Unsettled", "clear": "Clear"},
                "zh": {"storm": "暴风雨", "unsettled": "多变", "clear": "晴朗"},
                "es": {"storm": "Tormenta", "unsettled": "Inestable", "clear": "Despejado"},
                "fr": {"storm": "Tempête", "unsettled": "Instable", "clear": "Dégagé"},
                "pt": {"storm": "Tempestade", "unsettled": "Instável", "clear": "Céu limpo"},
                "id": {"storm": "Badai", "unsettled": "Tidak menentu", "clear": "Cerah"}},
    "today": {"en": "{business} today: {weather}.", "zh": "{business}今日现金天气：{weather}。",
              "es": "{business} hoy: {weather}.", "fr": "{business} aujourd'hui : {weather}.",
              "pt": "{business} hoje: {weather}.", "id": "{business} hari ini: {weather}."},
    "breach_scheduled": {"en": "Scheduled cash falls below the reserve on {date}; {short} of 20 simulated futures do too.",
                         "zh": "按计划，现金将在{date}跌破安全储备；20个模拟情景中有{short}个同样如此。",
                         "es": "Según lo programado, la caja cae por debajo de la reserva el {date}; también en {short} de 20 futuros simulados.",
                         "fr": "Selon le calendrier, la trésorerie passe sous la réserve le {date} ; c'est aussi le cas dans {short} futurs simulés sur 20.",
                         "pt": "Pelo cronograma, o caixa fica abaixo da reserva em {date}; o mesmo ocorre em {short} de 20 futuros simulados.",
                         "id": "Sesuai jadwal, kas turun di bawah cadangan pada {date}; begitu juga di {short} dari 20 skenario simulasi."},
    "breach_sim": {"en": "{short} of 20 simulated futures fall below the reserve.",
                   "zh": "20个模拟情景中有{short}个跌破安全储备。",
                   "es": "{short} de 20 futuros simulados caen por debajo de la reserva.",
                   "fr": "{short} futurs simulés sur 20 passent sous la réserve.",
                   "pt": "{short} de 20 futuros simulados ficam abaixo da reserva.",
                   "id": "{short} dari 20 skenario simulasi turun di bawah cadangan."},
    "lowest": {"en": "Lowest likely cash {amount} on {date}.", "zh": "最可能的最低现金为{amount}（{date}）。",
               "es": "Caja mínima probable: {amount} el {date}.", "fr": "Trésorerie minimale probable : {amount} le {date}.",
               "pt": "Caixa mínimo provável: {amount} em {date}.", "id": "Kas terendah yang mungkin {amount} pada {date}."},
    "payroll_due": {"en": "Payroll of {amount} is due {date}.", "zh": "{date}需支付工资{amount}。",
                    "es": "La nómina de {amount} vence el {date}.", "fr": "La paie de {amount} est due le {date}.",
                    "pt": "A folha de {amount} vence em {date}.", "id": "Gaji sebesar {amount} jatuh tempo {date}."},
    "attention": {"en": "Needs attention: {items}.", "zh": "需要关注：{items}。", "es": "Requiere atención: {items}.",
                  "fr": "À surveiller : {items}.", "pt": "Precisa de atenção: {items}.", "id": "Perlu perhatian: {items}."},
    "w_reserve_breach": {"en": "reserve breach scheduled", "zh": "计划内将跌破储备", "es": "ruptura de la reserva prevista",
                         "fr": "rupture de réserve prévue", "pt": "quebra da reserva prevista", "id": "cadangan diperkirakan jebol"},
    "w_payroll_at_risk": {"en": "payroll not fully funded", "zh": "工资资金不足", "es": "nómina sin fondos suficientes",
                          "fr": "paie non entièrement financée", "pt": "folha sem fundos suficientes", "id": "dana gaji belum cukup"},
    "w_payee_account_changed": {"en": "a supplier's bank details changed", "zh": "供应商银行账户被更改",
                                "es": "cambiaron los datos bancarios de un proveedor", "fr": "coordonnées bancaires d'un fournisseur modifiées",
                                "pt": "dados bancários de um fornecedor alterados", "id": "rekening pemasok berubah"},
    "w_lookalike_payee": {"en": "a look-alike payee name", "zh": "疑似仿冒的收款方名称", "es": "un beneficiario con nombre casi idéntico",
                          "fr": "un bénéficiaire au nom presque identique", "pt": "um beneficiário com nome quase idêntico",
                          "id": "nama penerima yang mirip"},
    "blocked": {"en": "{n} bill(s) are blocked for possible payment fraud.", "zh": "有{n}张账单因疑似支付欺诈被冻结。",
                "es": "{n} factura(s) bloqueada(s) por posible fraude de pago.", "fr": "{n} facture(s) bloquée(s) pour suspicion de fraude.",
                "pt": "{n} conta(s) bloqueada(s) por possível fraude de pagamento.", "id": "{n} tagihan diblokir karena dugaan penipuan pembayaran."},
    "plan_ready": {"en": "A rescue plan is ready (cost {amount}); it waits for a person to approve it.",
                   "zh": "救援方案已就绪（成本{amount}），等待人工批准。",
                   "es": "Hay un plan de rescate listo (coste {amount}); espera la aprobación de una persona.",
                   "fr": "Un plan de sauvetage est prêt (coût {amount}) ; il attend l'approbation d'une personne.",
                   "pt": "Há um plano de resgate pronto (custo {amount}); aguarda aprovação de uma pessoa.",
                   "id": "Rencana penyelamatan siap (biaya {amount}); menunggu persetujuan seseorang."},
    "ask_plan": {"en": "Ask me for a rescue plan.", "zh": "可以让我制定一个救援方案。", "es": "Pídeme un plan de rescate.",
                 "fr": "Demandez-moi un plan de sauvetage.", "pt": "Peça-me um plano de resgate.", "id": "Minta saya membuat rencana penyelamatan."},
    "all_good": {"en": "No action is needed right now.", "zh": "目前无需采取行动。", "es": "No hace falta actuar por ahora.",
                 "fr": "Aucune action n'est nécessaire pour l'instant.", "pt": "Nenhuma ação é necessária agora.",
                 "id": "Belum perlu tindakan apa pun."},
    "thanks": {"en": "You're welcome. Anything else?", "zh": "不客气。还有什么需要帮忙的吗？", "es": "De nada. ¿Algo más?",
               "fr": "Avec plaisir. Autre chose ?", "pt": "De nada. Mais alguma coisa?", "id": "Sama-sama. Ada lagi?"},
    "help": {"en": "I can tell you whether payroll is safe, how likely you are to run short, which customers pay late and what "
                   "TidePay expects from them, run a what-if, check if a customer is safe to sell to on credit, draft payment "
                   "reminders, build a rescue plan for a person to approve, and prepare a bank-ready pack. I never approve or "
                   "move money myself. Try one of the suggestions below.",
             "zh": "我可以告诉你工资是否发得出、资金短缺的可能性、哪些客户付款慢以及TidePay对他们的预测；可以做情景模拟、判断能否给客户赊账、"
                   "起草催款提醒、制定需人工批准的救援方案，并准备银行贷款材料。我从不自行批准或转账。试试下面的建议。",
             "es": "Puedo decirte si la nómina está cubierta, la probabilidad de quedarte sin caja, qué clientes pagan tarde y qué "
                   "espera TidePay de ellos, simular escenarios, evaluar si es seguro dar crédito a un cliente, redactar "
                   "recordatorios de pago, preparar un plan de rescate para que una persona lo apruebe y un dossier para el banco. "
                   "Nunca apruebo ni muevo dinero. Prueba una de las sugerencias.",
             "fr": "Je peux vous dire si la paie est couverte, le risque de manquer de trésorerie, quels clients paient en retard et "
                   "ce que TidePay prévoit, simuler des scénarios, évaluer un crédit client, rédiger des relances, préparer un "
                   "plan de sauvetage à faire approuver et un dossier bancaire. Je n'approuve et ne déplace jamais d'argent. "
                   "Essayez une suggestion ci-dessous.",
             "pt": "Posso dizer se a folha está coberta, a chance de faltar caixa, quais clientes pagam atrasado e o que o TidePay "
                   "espera deles, simular cenários, avaliar se é seguro vender a prazo, redigir lembretes de cobrança, montar um "
                   "plano de resgate para aprovação e um dossiê para o banco. Nunca aprovo nem movimento dinheiro. "
                   "Experimente uma sugestão abaixo.",
             "id": "Saya bisa memberi tahu apakah gaji aman, seberapa besar risiko kekurangan kas, pelanggan mana yang telat dan "
                   "perkiraan TidePay, membuat simulasi, menilai kelayakan kredit pelanggan, menyiapkan pengingat pembayaran, "
                   "menyusun rencana penyelamatan untuk disetujui, dan berkas pinjaman bank. Saya tidak pernah menyetujui atau "
                   "memindahkan uang. Coba salah satu saran di bawah."},
    "not_understood": {"en": "I'm not sure what you mean. I'm Tideway's cash-flow copilot for {business}: ask about cash, payroll, "
                             "customers, risk or a rescue plan, in your own words and language. For example:",
                       "zh": "我不太明白你的意思。我是{business}的现金流助手：可以用你自己的话问我现金、工资、客户、风险或救援方案。例如：",
                       "es": "No estoy seguro de qué quieres decir. Soy el copiloto de caja de {business}: pregúntame por la caja, "
                             "la nómina, los clientes, el riesgo o un plan de rescate. Por ejemplo:",
                       "fr": "Je ne suis pas sûr de comprendre. Je suis le copilote de trésorerie de {business} : interrogez-moi "
                             "sur la trésorerie, la paie, les clients, le risque ou un plan de sauvetage. Par exemple :",
                       "pt": "Não tenho certeza do que você quer dizer. Sou o copiloto de caixa da {business}: pergunte sobre caixa, "
                             "folha, clientes, risco ou um plano de resgate. Por exemplo:",
                       "id": "Saya kurang paham maksudnya. Saya kopilot arus kas {business}: tanyakan soal kas, gaji, pelanggan, "
                             "risiko, atau rencana penyelamatan. Contohnya:"},
    "out_of_scope": {"en": "That's outside what I do; I only work on this business's cash flow. I can answer questions about "
                           "payroll, risk, customers, what-ifs, credit checks, reminders and rescue plans.",
                     "zh": "这超出了我的范围；我只处理这家企业的现金流。我可以回答工资、风险、客户、情景模拟、赊账评估、催款和救援方案的问题。",
                     "es": "Eso queda fuera de lo que hago; solo trabajo con la caja de este negocio. Puedo responder sobre nómina, "
                           "riesgo, clientes, escenarios, crédito, recordatorios y planes de rescate.",
                     "fr": "Cela sort de mon rôle : je ne traite que la trésorerie de cette entreprise. Je peux répondre sur la paie, "
                           "le risque, les clients, les scénarios, le crédit, les relances et les plans de sauvetage.",
                     "pt": "Isso está fora do que faço; só trabalho com o caixa deste negócio. Posso responder sobre folha, risco, "
                           "clientes, cenários, crédito, lembretes e planos de resgate.",
                     "id": "Itu di luar tugas saya; saya hanya menangani arus kas bisnis ini. Saya bisa menjawab soal gaji, risiko, "
                           "pelanggan, simulasi, kredit, pengingat, dan rencana penyelamatan."},
    "refuse_money": {"en": "I can't approve, pay or transfer money; a person approves in the app with a PIN.",
                     "zh": "我不能批准、付款或转账；必须由人在应用中输入PIN批准。",
                     "es": "No puedo aprobar, pagar ni transferir dinero; una persona aprueba en la app con su PIN.",
                     "fr": "Je ne peux ni approuver, ni payer, ni virer d'argent ; une personne approuve dans l'application avec son code PIN.",
                     "pt": "Não posso aprovar, pagar nem transferir dinheiro; uma pessoa aprova no app com o PIN.",
                     "id": "Saya tidak bisa menyetujui, membayar, atau mentransfer uang; seseorang menyetujuinya di aplikasi dengan PIN."},
    "viewer": {"en": "Viewers can read forecasts and reports, but only an owner or accountant can ask for plans or reminders.",
               "zh": "查看者可以阅读预测和报告，但只有所有者或会计可以请求方案或提醒。",
               "es": "Los observadores pueden leer previsiones e informes, pero solo el dueño o el contador pueden pedir planes o recordatorios.",
               "fr": "Les lecteurs peuvent consulter prévisions et rapports, mais seuls le propriétaire ou le comptable peuvent demander des plans ou des relances.",
               "pt": "Visualizadores podem ler previsões e relatórios, mas só o dono ou o contador podem pedir planos ou lembretes.",
               "id": "Peninjau dapat membaca proyeksi dan laporan, tetapi hanya pemilik atau akuntan yang dapat meminta rencana atau pengingat."},
    "no_customer": {"en": "I couldn't match a customer in that question to this business's ledger, so I won't guess. "
                          "Use the ledger spelling: {names}.",
                    "zh": "问题中的客户与本企业账本不符，我不会猜测。请使用账本中的名称：{names}。",
                    "es": "No encontré a ese cliente en el libro de esta empresa, así que no voy a adivinar. "
                          "Usa el nombre como figura en el libro: {names}.",
                    "fr": "Je ne trouve pas ce client dans le registre de cette entreprise, je ne devine donc pas. "
                          "Utilisez le nom tel qu'il figure au registre : {names}.",
                    "pt": "Não encontrei esse cliente no livro desta empresa, então não vou adivinhar. "
                          "Use o nome como está no livro: {names}.",
                    "id": "Saya tidak menemukan pelanggan itu di buku besar bisnis ini, jadi saya tidak menebak. "
                          "Gunakan ejaan di buku besar: {names}."},
    "unsafe": {"en": "I couldn't do that safely: {reason}", "zh": "我无法安全地完成：{reason}",
               "es": "No pude hacerlo de forma segura: {reason}", "fr": "Je n'ai pas pu le faire en toute sécurité : {reason}",
               "pt": "Não consegui fazer isso com segurança: {reason}", "id": "Saya tidak bisa melakukannya dengan aman: {reason}"},
    "scenario": {"en": {"base": "Scheduled", "likely": "Likely", "stress": "Stress"}, "zh": {"base": "按计划", "likely": "最可能", "stress": "压力"},
                 "es": {"base": "Programado", "likely": "Probable", "stress": "Estrés"}, "fr": {"base": "Prévu", "likely": "Probable", "stress": "Stress"},
                 "pt": {"base": "Programado", "likely": "Provável", "stress": "Estresse"}, "id": {"base": "Terjadwal", "likely": "Kemungkinan", "stress": "Tekanan"}},
    "projection": {"en": "{scenario} view: lowest cash {amount} on {date}; reserve shortfall {short}; {payroll}",
                   "zh": "{scenario}情景：最低现金{amount}（{date}）；储备缺口{short}；{payroll}",
                   "es": "Escenario {scenario}: caja mínima {amount} el {date}; déficit de reserva {short}; {payroll}",
                   "fr": "Vue {scenario} : trésorerie minimale {amount} le {date} ; manque à la réserve {short} ; {payroll}",
                   "pt": "Cenário {scenario}: caixa mínimo {amount} em {date}; falta na reserva {short}; {payroll}",
                   "id": "Skenario {scenario}: kas terendah {amount} pada {date}; kekurangan cadangan {short}; {payroll}"},
    "payroll_ok": {"en": "payroll is funded.", "zh": "工资有保障。", "es": "la nómina está cubierta.", "fr": "la paie est couverte.",
                   "pt": "a folha está coberta.", "id": "gaji aman."},
    "payroll_risk": {"en": "payroll is at risk.", "zh": "工资存在风险。", "es": "la nómina está en riesgo.", "fr": "la paie est menacée.",
                     "pt": "a folha está em risco.", "id": "gaji berisiko."},
    "risk": {"en": "{short} of 20 simulated futures breach the reserve; payroll is unfunded in {payroll}% of {runs} runs.",
             "zh": "20个模拟情景中有{short}个跌破储备；在{runs}次模拟中，有{payroll}%的情况工资资金不足。",
             "es": "{short} de 20 futuros simulados rompen la reserva; la nómina queda sin fondos en el {payroll}% de {runs} simulaciones.",
             "fr": "{short} futurs simulés sur 20 passent sous la réserve ; la paie n'est pas financée dans {payroll} % des {runs} simulations.",
             "pt": "{short} de 20 futuros simulados quebram a reserva; a folha fica sem fundos em {payroll}% de {runs} simulações.",
             "id": "{short} dari 20 skenario simulasi menembus cadangan; gaji tidak terdanai di {payroll}% dari {runs} simulasi."},
    "whatif": {"en": "With that change, the lowest likely cash is {amount} on {date}: {change}. Reserve shortfall {short}. Nothing was saved.",
               "zh": "在这种情况下，最可能的最低现金为{amount}（{date}）：{change}。储备缺口{short}。未保存任何更改。",
               "es": "Con ese cambio, la caja mínima probable sería {amount} el {date}: {change}. Déficit de reserva {short}. No se guardó nada.",
               "fr": "Avec ce changement, la trésorerie minimale probable serait de {amount} le {date} : {change}. Manque à la réserve {short}. Rien n'a été enregistré.",
               "pt": "Com essa mudança, o caixa mínimo provável seria {amount} em {date}: {change}. Falta na reserva {short}. Nada foi salvo.",
               "id": "Dengan perubahan itu, kas terendah yang mungkin {amount} pada {date}: {change}. Kekurangan cadangan {short}. Tidak ada yang disimpan."},
    "worse": {"en": "{amount} worse than today's likely low of {base}", "zh": "比当前最可能的低点{base}还少{amount}",
              "es": "{amount} peor que el mínimo probable actual de {base}", "fr": "{amount} de moins que le minimum probable actuel de {base}",
              "pt": "{amount} pior que o mínimo provável atual de {base}", "id": "{amount} lebih buruk dari titik terendah saat ini {base}"},
    "better": {"en": "{amount} better than today's likely low", "zh": "比当前最可能的低点多{amount}",
               "es": "{amount} mejor que el mínimo probable actual", "fr": "{amount} de mieux que le minimum probable actuel",
               "pt": "{amount} melhor que o mínimo provável atual", "id": "{amount} lebih baik dari titik terendah saat ini"},
    "same": {"en": "no worse than today's likely low", "zh": "与当前最可能的低点相同", "es": "igual que el mínimo probable actual",
             "fr": "identique au minimum probable actuel", "pt": "igual ao mínimo provável atual", "id": "sama dengan titik terendah saat ini"},
    "plan_none": {"en": "No action needed: cash stays at or above the reserve floor through the planning horizon.",
                  "zh": "无需行动：在整个规划期内，现金始终不低于安全储备。",
                  "es": "No hace falta actuar: la caja se mantiene por encima de la reserva durante todo el horizonte.",
                  "fr": "Aucune action nécessaire : la trésorerie reste au-dessus de la réserve sur tout l'horizon.",
                  "pt": "Nenhuma ação necessária: o caixa fica acima da reserva durante todo o horizonte.",
                  "id": "Tidak perlu tindakan: kas tetap di atas cadangan sepanjang periode perencanaan."},
    "plan_gap": {"en": "Without action, cash falls to {amount} on {date}: {short} below the reserve floor.",
                 "zh": "如果不采取行动，现金将在{date}降至{amount}，比安全储备低{short}。",
                 "es": "Sin actuar, la caja cae a {amount} el {date}: {short} por debajo de la reserva.",
                 "fr": "Sans action, la trésorerie tombe à {amount} le {date} : {short} sous la réserve.",
                 "pt": "Sem ação, o caixa cai para {amount} em {date}: {short} abaixo da reserva.",
                 "id": "Tanpa tindakan, kas turun ke {amount} pada {date}: {short} di bawah cadangan."},
    "plan_recommend": {"en": "Recommended: {actions}. Economic cost {cost}; {n} counterparties must agree; {after} of 20 simulated futures still fall short.",
                       "zh": "建议：{actions}。经济成本{cost}；需要{n}个对方同意；20个模拟情景中仍有{after}个不足。",
                       "es": "Recomendado: {actions}. Coste económico {cost}; {n} contrapartes deben aceptar; {after} de 20 futuros simulados siguen quedándose cortos.",
                       "fr": "Recommandé : {actions}. Coût économique {cost} ; {n} contreparties doivent accepter ; {after} futurs simulés sur 20 restent insuffisants.",
                       "pt": "Recomendado: {actions}. Custo econômico {cost}; {n} contrapartes devem aceitar; {after} de 20 futuros simulados ainda ficam curtos.",
                       "id": "Rekomendasi: {actions}. Biaya ekonomi {cost}; {n} pihak harus setuju; {after} dari 20 skenario simulasi masih kurang."},
    "plan_nosafe": {"en": "No safe combination exists within policy; the strongest leaves {short} uncovered. Escalate to the owner.",
                    "zh": "在政策范围内没有安全的组合；最强方案仍有{short}缺口，需上报所有者。",
                    "es": "No existe una combinación segura dentro de la política; la mejor deja {short} sin cubrir. Escala al dueño.",
                    "fr": "Aucune combinaison sûre n'existe dans la politique ; la meilleure laisse {short} non couvert. Remontez au propriétaire.",
                    "pt": "Não há combinação segura dentro da política; a melhor deixa {short} descoberto. Escale ao dono.",
                    "id": "Tidak ada kombinasi aman sesuai kebijakan; yang terkuat masih menyisakan {short}. Teruskan ke pemilik."},
    "plan_wait": {"en": "It is waiting for human approval in the Rescue plan view.", "zh": "方案正在“救援方案”页面等待人工批准。",
                  "es": "Está esperando aprobación humana en la vista del plan de rescate.",
                  "fr": "Il attend une approbation humaine dans la vue du plan de sauvetage.",
                  "pt": "Está aguardando aprovação humana na tela do plano de resgate.",
                  "id": "Menunggu persetujuan manusia di tampilan rencana penyelamatan."},
    "act_defer": {"en": "ask {who} to move {amount} from {from_} to {to}", "zh": "请{who}将{amount}从{from_}推迟到{to}",
                  "es": "pedir a {who} mover {amount} del {from_} al {to}", "fr": "demander à {who} de décaler {amount} du {from_} au {to}",
                  "pt": "pedir a {who} para adiar {amount} de {from_} para {to}", "id": "minta {who} memundurkan {amount} dari {from_} ke {to}"},
    "act_early": {"en": "offer {who} {pct}% off to pay {amount} by {to}", "zh": "给{who}提供{pct}%折扣，请其在{to}前支付{amount}",
                  "es": "ofrecer a {who} un {pct}% de descuento por pagar {amount} antes del {to}",
                  "fr": "proposer à {who} {pct} % de remise pour payer {amount} avant le {to}",
                  "pt": "oferecer a {who} {pct}% de desconto para pagar {amount} até {to}",
                  "id": "tawarkan {who} diskon {pct}% untuk membayar {amount} paling lambat {to}"},
    "why_best": {"en": "I recommend this bundle because it holds the reserve floor every day with payroll funded, and only {after} of 20 simulated futures still fall short (my bar is {target} or fewer), at an economic cost of {cost}.",
                 "zh": "我推荐这个组合，因为它每天都守住安全储备、保证工资发放，20个模拟情景中只有{after}个仍不足（我的标准是不超过{target}个），经济成本为{cost}。",
                 "es": "Recomiendo este paquete porque mantiene la reserva todos los días con la nómina cubierta, y solo {after} de 20 futuros simulados se quedan cortos (mi límite es {target} o menos), con un coste económico de {cost}.",
                 "fr": "Je recommande ce lot car il tient la réserve chaque jour avec la paie couverte, et seuls {after} futurs simulés sur 20 restent insuffisants (mon seuil est de {target} ou moins), pour un coût économique de {cost}.",
                 "pt": "Recomendo este pacote porque mantém a reserva todos os dias com a folha coberta, e só {after} de 20 futuros simulados ficam curtos (meu limite é {target} ou menos), com custo econômico de {cost}.",
                 "id": "Saya merekomendasikan paket ini karena menjaga cadangan setiap hari dengan gaji terdanai, dan hanya {after} dari 20 skenario simulasi yang masih kurang (batas saya {target} atau kurang), dengan biaya ekonomi {cost}."},
    "why_risky": {"en": "Another option ({cost}) leaves {after} of 20 futures short: too risky.",
                  "zh": "另一个方案（{cost}）仍有{after}/20个情景不足：风险太高。",
                  "es": "Otra opción ({cost}) deja {after} de 20 futuros cortos: demasiado arriesgada.",
                  "fr": "Une autre option ({cost}) laisse {after} futurs sur 20 insuffisants : trop risquée.",
                  "pt": "Outra opção ({cost}) deixa {after} de 20 futuros curtos: arriscada demais.",
                  "id": "Opsi lain ({cost}) menyisakan {after} dari 20 skenario kurang: terlalu berisiko."},
    "why_costlier": {"en": "Another safe option costs {gap} more and asks {n} counterparties.",
                     "zh": "另一个安全方案多花{gap}，且需要{n}个对方同意。",
                     "es": "Otra opción segura cuesta {gap} más y requiere {n} contrapartes.",
                     "fr": "Une autre option sûre coûte {gap} de plus et sollicite {n} contreparties.",
                     "pt": "Outra opção segura custa {gap} a mais e envolve {n} contrapartes.",
                     "id": "Opsi aman lain lebih mahal {gap} dan melibatkan {n} pihak."},
    "why_alone": {"en": "No single action is enough: the best request to {who} alone still leaves you {short} short.",
                  "zh": "单一行动不够：仅靠{who}的最佳方案仍差{short}。",
                  "es": "Ninguna acción sola basta: la mejor solicitud a {who} por sí sola aún deja un faltante de {short}.",
                  "fr": "Aucune action seule ne suffit : la meilleure demande à {who} laisse encore {short} de manque.",
                  "pt": "Nenhuma ação sozinha basta: o melhor pedido a {who} ainda deixa {short} faltando.",
                  "id": "Tidak ada satu tindakan yang cukup: permintaan terbaik ke {who} saja masih kurang {short}."},
    "why_finance": {"en": "The cheapest financing would cost {fee} in fees (illustrative mock offer), so it is kept as a fallback.",
                    "zh": "最便宜的融资需支付{fee}手续费（示意性模拟报价），因此仅作为备选。",
                    "es": "La financiación más barata costaría {fee} en comisiones (oferta simulada ilustrativa), así que queda como alternativa.",
                    "fr": "Le financement le moins cher coûterait {fee} de frais (offre fictive illustrative) ; il reste une solution de repli.",
                    "pt": "O financiamento mais barato custaria {fee} em taxas (oferta simulada ilustrativa), então fica como alternativa.",
                    "id": "Pembiayaan termurah akan menelan biaya {fee} (penawaran simulasi ilustratif), jadi disimpan sebagai cadangan."},
    "no_plan": {"en": "There is no current proposal yet. Ask me for a rescue plan first.", "zh": "目前还没有方案。请先让我制定救援方案。",
                "es": "Todavía no hay propuesta. Pídeme primero un plan de rescate.", "fr": "Il n'y a pas encore de proposition. Demandez-moi d'abord un plan de sauvetage.",
                "pt": "Ainda não há proposta. Peça-me primeiro um plano de resgate.", "id": "Belum ada usulan. Minta saya membuat rencana penyelamatan dulu."},
    "credit": {"en": "Credit check for {who} ({amount}, {days} days): {verdict}. {advice} {reasons}.",
               "zh": "{who}的赊账评估（{amount}，{days}天）：{verdict}。{advice}{reasons}。",
               "es": "Evaluación de crédito de {who} ({amount}, {days} días): {verdict}. {advice} {reasons}.",
               "fr": "Analyse de crédit de {who} ({amount}, {days} jours) : {verdict}. {advice} {reasons}.",
               "pt": "Análise de crédito de {who} ({amount}, {days} dias): {verdict}. {advice} {reasons}.",
               "id": "Cek kredit {who} ({amount}, {days} hari): {verdict}. {advice} {reasons}."},
    "verdict": {"en": {"safe": "SAFE", "caution": "CAUTION", "high_risk": "HIGH RISK"}, "zh": {"safe": "安全", "caution": "谨慎", "high_risk": "高风险"},
                "es": {"safe": "SEGURO", "caution": "PRECAUCIÓN", "high_risk": "RIESGO ALTO"}, "fr": {"safe": "SÛR", "caution": "PRUDENCE", "high_risk": "RISQUE ÉLEVÉ"},
                "pt": {"safe": "SEGURO", "caution": "CAUTELA", "high_risk": "RISCO ALTO"}, "id": {"safe": "AMAN", "caution": "WASPADA", "high_risk": "RISIKO TINGGI"}},
    "advice_high_risk": {"en": "Ask for at least 50% upfront or cash on delivery; do not extend full credit.", "zh": "要求至少预付50%或货到付款，不要全额赊账。",
                         "es": "Pide al menos un 50% por adelantado o pago contra entrega; no concedas crédito completo.",
                         "fr": "Demandez au moins 50 % d'acompte ou un paiement à la livraison ; pas de crédit total.",
                         "pt": "Peça pelo menos 50% adiantado ou pagamento na entrega; não conceda crédito total.",
                         "id": "Minta uang muka minimal 50% atau bayar di tempat; jangan beri kredit penuh."},
    "advice_caution": {"en": "Offer shorter terms or take a 30% deposit.", "zh": "缩短账期或收取30%定金。",
                       "es": "Ofrece plazos más cortos o pide un depósito del 30%.", "fr": "Proposez des délais plus courts ou un acompte de 30 %.",
                       "pt": "Ofereça prazos menores ou peça um sinal de 30%.", "id": "Tawarkan tenor lebih pendek atau minta uang muka 30%."},
    "advice_safe": {"en": "These terms look safe based on this customer's history.", "zh": "根据该客户的历史，这些条件看起来是安全的。",
                    "es": "Estos plazos parecen seguros según el historial del cliente.", "fr": "Ces conditions semblent sûres au vu de l'historique du client.",
                    "pt": "Esses prazos parecem seguros pelo histórico do cliente.", "id": "Syarat ini tampak aman berdasarkan riwayat pelanggan."},
    "advice_concentration": {"en": "The customer pays well, but this sale concentrates too much risk in one account; consider a deposit.",
                             "zh": "该客户付款良好，但这笔销售会让风险过度集中在一个客户身上，建议收取定金。",
                             "es": "El cliente paga bien, pero esta venta concentra demasiado riesgo en una sola cuenta; considera un depósito.",
                             "fr": "Le client paie bien, mais cette vente concentre trop de risque sur un seul compte ; envisagez un acompte.",
                             "pt": "O cliente paga bem, mas essa venda concentra risco demais em uma só conta; considere um sinal.",
                             "id": "Pelanggan membayar dengan baik, tetapi penjualan ini memusatkan risiko pada satu akun; pertimbangkan uang muka."},
    "r_history": {"en": "{n} settled invoice(s) on record, average {late} days late", "zh": "已有{n}张结清发票，平均逾期{late}天",
                  "es": "{n} factura(s) cobrada(s), con {late} días de retraso de media", "fr": "{n} facture(s) réglée(s), {late} jours de retard en moyenne",
                  "pt": "{n} fatura(s) quitada(s), média de {late} dias de atraso", "id": "{n} faktur lunas, rata-rata telat {late} hari"},
    "r_nohistory": {"en": "no history yet, so the business-wide pattern is used", "zh": "暂无历史，采用整体付款规律",
                    "es": "sin historial, se usa el patrón general del negocio", "fr": "pas d'historique, le profil global de l'entreprise est utilisé",
                    "pt": "sem histórico, usa-se o padrão geral do negócio", "id": "belum ada riwayat, jadi pola umum bisnis dipakai"},
    "r_tidepay": {"en": "TidePay expects about {days} days of delay ({p30}% chance of more than 30 days)",
                  "zh": "TidePay预计约延迟{days}天（超过30天的概率为{p30}%）",
                  "es": "TidePay prevé unos {days} días de retraso ({p30}% de probabilidad de más de 30 días)",
                  "fr": "TidePay prévoit environ {days} jours de retard ({p30} % de risque de plus de 30 jours)",
                  "pt": "O TidePay prevê cerca de {days} dias de atraso ({p30}% de chance de mais de 30 dias)",
                  "id": "TidePay memperkirakan telat sekitar {days} hari (peluang {p30}% lebih dari 30 hari)"},
    "r_arrival": {"en": "expected payment around {date}", "zh": "预计付款日约为{date}", "es": "pago esperado hacia el {date}",
                  "fr": "paiement attendu vers le {date}", "pt": "pagamento esperado por volta de {date}", "id": "perkiraan pembayaran sekitar {date}"},
    "r_share": {"en": "after this sale {share}% of all money owed to you would sit with {who}", "zh": "这笔销售后，你所有应收款中有{share}%集中在{who}",
                "es": "tras esta venta, el {share}% de lo que te deben estaría en manos de {who}",
                "fr": "après cette vente, {share} % de vos créances seraient chez {who}",
                "pt": "depois desta venda, {share}% de tudo o que lhe devem ficaria com {who}",
                "id": "setelah penjualan ini, {share}% piutang Anda ada di {who}"},
    "customer": {"en": "{who}: grade {grade}, TidePay expects about {late} days late on the open invoice, {open} open",
                 "zh": "{who}：评级{grade}，TidePay预计未结发票约逾期{late}天，未收{open}",
                 "es": "{who}: calificación {grade}, TidePay prevé unos {late} días de retraso en la factura abierta, {open} pendiente",
                 "fr": "{who} : note {grade}, TidePay prévoit environ {late} jours de retard sur la facture ouverte, {open} en attente",
                 "pt": "{who}: nota {grade}, o TidePay prevê cerca de {late} dias de atraso na fatura aberta, {open} em aberto",
                 "id": "{who}: peringkat {grade}, TidePay memperkirakan telat sekitar {late} hari pada faktur terbuka, {open} belum dibayar"},
    "drafts": {"en": "{n} reminder draft(s) ready: {names}. Review and send them from the Rescue plan view.",
               "zh": "已准备{n}份催款草稿：{names}。请在“救援方案”页面审核并发送。",
               "es": "{n} borrador(es) de recordatorio listo(s): {names}. Revísalos y envíalos desde el plan de rescate.",
               "fr": "{n} brouillon(s) de relance prêt(s) : {names}. Vérifiez-les et envoyez-les depuis le plan de sauvetage.",
               "pt": "{n} rascunho(s) de lembrete pronto(s): {names}. Revise e envie pela tela do plano de resgate.",
               "id": "{n} draf pengingat siap: {names}. Tinjau dan kirim dari tampilan rencana penyelamatan."},
    "bank_pack": {"en": "Your bank-ready pack is prepared: cash history, receivables aging, forecast, risk and plan. Download it from Cash weather (Bank-ready pack).",
                  "zh": "银行贷款材料已备好：现金历史、应收账龄、预测、风险和方案。可在“现金天气”中下载（银行材料）。",
                  "es": "Tu dossier para el banco está listo: historial de caja, antigüedad de cobros, previsión, riesgo y plan. Descárgalo desde el clima de caja (dossier para el banco).",
                  "fr": "Votre dossier bancaire est prêt : historique de trésorerie, balance âgée, prévision, risque et plan. Téléchargez-le depuis la météo de trésorerie (dossier bancaire).",
                  "pt": "Seu dossiê para o banco está pronto: histórico de caixa, aging de recebíveis, previsão, risco e plano. Baixe pelo clima do caixa (dossiê para o banco).",
                  "id": "Berkas siap-bank Anda sudah disiapkan: riwayat kas, umur piutang, proyeksi, risiko, dan rencana. Unduh dari cuaca kas (berkas siap-bank)."},
    "network_top": {"en": "{who} is your biggest counterparty risk: TidePay gives a {p30}% chance of paying more than 30 days late, and if they never pay you lose {loss} of cash by {date} ({days} more day(s) under the reserve).",
                    "zh": "{who}是你最大的交易对手风险：TidePay预计其逾期超过30天的概率为{p30}%；如果对方一直不付款，到{date}你将损失{loss}现金（低于储备的天数增加{days}天）。",
                    "es": "{who} es tu mayor riesgo de contraparte: TidePay estima un {p30}% de probabilidad de pagar con más de 30 días de retraso, y si nunca paga pierdes {loss} de caja antes del {date} ({days} día(s) más bajo la reserva).",
                    "fr": "{who} est votre plus grand risque de contrepartie : TidePay estime à {p30} % le risque d'un retard de plus de 30 jours, et s'il ne paie jamais vous perdez {loss} de trésorerie d'ici le {date} ({days} jour(s) de plus sous la réserve).",
                    "pt": "{who} é o seu maior risco de contraparte: o TidePay estima {p30}% de chance de pagar com mais de 30 dias de atraso, e se nunca pagar você perde {loss} de caixa até {date} ({days} dia(s) a mais abaixo da reserva).",
                    "id": "{who} adalah risiko pihak lawan terbesar Anda: TidePay memperkirakan peluang {p30}% telat lebih dari 30 hari, dan jika tidak membayar sama sekali Anda kehilangan kas {loss} sebelum {date} ({days} hari lagi di bawah cadangan)."},
    "network_outside": {"en": "{who} is the riskiest payer (TidePay: {p30}% chance of more than 30 days late), but its payment is not expected before {date}, so your forecast already does not count on it.",
                        "zh": "{who}是风险最高的付款方（TidePay：逾期超过30天的概率为{p30}%），但其付款预计不会在{date}前到账，因此你的预测本就没有计入这笔钱。",
                        "es": "{who} es el pagador más arriesgado (TidePay: {p30}% de probabilidad de más de 30 días de retraso), pero su pago no se espera antes del {date}, así que tu previsión ya no cuenta con él.",
                        "fr": "{who} est le payeur le plus risqué (TidePay : {p30} % de risque de plus de 30 jours de retard), mais son paiement n'est pas attendu avant le {date} ; votre prévision ne compte donc déjà pas dessus.",
                        "pt": "{who} é o pagador mais arriscado (TidePay: {p30}% de chance de mais de 30 dias de atraso), mas o pagamento não é esperado antes de {date}, então sua previsão já não conta com ele.",
                        "id": "{who} adalah pembayar paling berisiko (TidePay: peluang {p30}% telat lebih dari 30 hari), tetapi pembayarannya tidak diharapkan sebelum {date}, jadi proyeksi Anda memang tidak mengandalkannya."},
    "network_empty": {"en": "No open receivables, so no customer can delay your cash.", "zh": "没有未收账款，因此没有客户会拖延你的现金。",
                      "es": "No hay cobros pendientes, así que ningún cliente puede retrasar tu caja.", "fr": "Aucune créance ouverte : aucun client ne peut retarder votre trésorerie.",
                      "pt": "Não há recebíveis em aberto, então nenhum cliente pode atrasar seu caixa.", "id": "Tidak ada piutang terbuka, jadi tidak ada pelanggan yang bisa menunda kas Anda."},
    "paused": {"en": "The agent is paused by the kill switch.", "zh": "代理已被紧急开关暂停。", "es": "El agente está en pausa por el interruptor de emergencia.",
               "fr": "L'agent est en pause (arrêt d'urgence).", "pt": "O agente está pausado pelo botão de emergência.", "id": "Agen sedang dihentikan oleh tombol darurat."},
    "blocked_list": {"en": "{n} bill(s) are blocked: {items}.", "zh": "有{n}张账单被冻结：{items}。", "es": "{n} factura(s) bloqueada(s): {items}.",
                     "fr": "{n} facture(s) bloquée(s) : {items}.", "pt": "{n} conta(s) bloqueada(s): {items}.", "id": "{n} tagihan diblokir: {items}."},
    "b_changed": {"en": "{payee} (bank details changed: verify by calling a number already on file)", "zh": "{payee}（银行账户被更改：请拨打档案中的号码核实）",
                  "es": "{payee} (cambiaron sus datos bancarios: verifica llamando a un número que ya tengas)",
                  "fr": "{payee} (coordonnées bancaires modifiées : vérifiez en appelant un numéro déjà connu)",
                  "pt": "{payee} (dados bancários alterados: confirme ligando para um número já cadastrado)",
                  "id": "{payee} (rekening berubah: verifikasi dengan menelepon nomor yang sudah tercatat)"},
    "b_lookalike": {"en": "{payee} (name looks like {similar}: possible impostor)", "zh": "{payee}（名称与{similar}极为相似：可能是冒充者）",
                    "es": "{payee} (nombre casi igual a {similar}: posible impostor)", "fr": "{payee} (nom presque identique à {similar} : imposteur possible)",
                    "pt": "{payee} (nome quase igual a {similar}: possível impostor)", "id": "{payee} (nama mirip {similar}: kemungkinan penipu)"},
    "nothing_blocked": {"en": "No bills are blocked.", "zh": "没有被冻结的账单。", "es": "No hay facturas bloqueadas.", "fr": "Aucune facture n'est bloquée.",
                        "pt": "Nenhuma conta está bloqueada.", "id": "Tidak ada tagihan yang diblokir."},
    "quarantined": {"en": "{n} stored record(s) contain instruction-like text and are quarantined; they are not used as model context or instructions.",
                    "zh": "有{n}条已保存记录含有类似指令的文字，已被隔离，不会作为模型上下文或指令使用。",
                    "es": "{n} registro(s) guardado(s) contienen texto con apariencia de instrucciones y están en cuarentena; no se usan como contexto ni instrucciones del modelo.",
                    "fr": "{n} enregistrement(s) enregistré(s) contiennent un texte ressemblant à des instructions et sont en quarantaine ; ils ne servent pas de contexte ni d'instruction au modèle.",
                    "pt": "{n} registro(s) salvo(s) contêm texto com cara de instrução e estão em quarentena; não são usados como contexto nem instrução do modelo.",
                    "id": "{n} catatan tersimpan berisi teks mirip perintah dan dikarantina; tidak digunakan sebagai konteks atau instruksi model."},
}

SUGGESTIONS = {
    "payroll": {"en": "Can I pay salaries this month?", "zh": "这个月工资发得出来吗？", "es": "¿Puedo pagar los sueldos este mes?",
                "fr": "Est-ce que je peux payer les salaires ce mois-ci ?", "pt": "Consigo pagar os salários este mês?", "id": "Bisa bayar gaji karyawan bulan ini?"},
    "rescue": {"en": "Find me a rescue plan", "zh": "帮我做一个资金缺口方案", "es": "Hazme un plan de rescate", "fr": "Propose-moi un plan de sauvetage",
               "pt": "Faça um plano para cobrir o caixa", "id": "Buatkan rencana penyelamatan kas"},
    "why": {"en": "Why this plan?", "zh": "为什么推荐这个方案？", "es": "¿Por qué este plan?", "fr": "Pourquoi ce plan ?", "pt": "Por que este plano?",
            "id": "Kenapa rencana ini?"},
    "risk": {"en": "How risky is this month?", "zh": "这个月现金风险有多大？", "es": "¿Qué tan arriesgado es este mes?",
             "fr": "Quel est le risque de manquer de trésorerie ?", "pt": "Qual o risco de faltar caixa este mês?", "id": "Seberapa besar risiko kas bulan ini?"},
    "forecast": {"en": "Show the cash forecast", "zh": "给我看现金流预测", "es": "Muéstrame la previsión de caja", "fr": "Montre-moi la prévision de trésorerie",
                 "pt": "Mostre a previsão de caixa", "id": "Tunjukkan proyeksi arus kas"},
    "late": {"en": "Which customers pay late?", "zh": "哪些客户付款最慢？", "es": "¿Qué clientes pagan tarde?", "fr": "Quels clients paient en retard ?",
             "pt": "Quais clientes pagam com atraso?", "id": "Pelanggan mana yang paling lambat bayar?"},
    "remind": {"en": "Remind everyone who owes me", "zh": "提醒所有欠款客户", "es": "Recuerda a todos los que me deben",
               "fr": "Relance tous les clients en retard", "pt": "Cobre todos os clientes atrasados", "id": "Ingatkan semua pelanggan yang telat"},
    "blocked": {"en": "Which bills are blocked and why?", "zh": "哪些账单被冻结了，为什么？", "es": "¿Qué facturas están bloqueadas y por qué?",
                "fr": "Quelles factures sont bloquées et pourquoi ?", "pt": "Quais contas estão bloqueadas e por quê?", "id": "Tagihan mana yang diblokir dan kenapa?"},
    "whatif": {"en": "What if {who} pays {days} days late?", "zh": "如果{who}晚{days}天付款会怎样？", "es": "¿Qué pasa si {who} paga {days} días tarde?",
               "fr": "Et si {who} paie avec {days} jours de retard ?", "pt": "E se {who} pagar com {days} dias de atraso?",
               "id": "Bagaimana kalau {who} telat bayar {days} hari?"},
    "habit": {"en": "How does {who} usually pay?", "zh": "{who}一般按时付款吗？", "es": "¿Cómo suele pagar {who}?", "fr": "Comment paie {who} d'habitude ?",
              "pt": "Como {who} costuma pagar?", "id": "{who} biasanya bayar tepat waktu?"},
    "network": {"en": "Who is my biggest risk?", "zh": "谁是我最大的风险？", "es": "¿Quién es mi mayor riesgo?", "fr": "Qui est mon plus grand risque ?",
                "pt": "Quem é o meu maior risco?", "id": "Siapa risiko terbesar saya?"},
    "credit": {"en": "Should I give {who} 30 days credit on 20,000?", "zh": "{who}要赊账20000，账期30天，可以吗？",
               "es": "¿Le doy a {who} crédito de 20000 a 30 días?", "fr": "Puis-je accorder à {who} 20000 à 30 jours ?",
               "pt": "Posso vender 20000 para {who} com 30 dias de prazo?", "id": "Aman tidak kasih {who} kredit 20000 tempo 30 hari?"},
}


def t(lang, key, **values):
    table = M[key]
    template = table.get(lang) or table["en"]
    return template.format(**values) if isinstance(template, str) else template


def ask(lang, key, **values):
    table = SUGGESTIONS[key]
    return (table.get(lang) or table["en"]).format(**values)


def money(minor, currency):
    return money_text(minor, currency)
