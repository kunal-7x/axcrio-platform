# Haptica advanced LLM benchmark (v2, Groq pool)

## #1 sarvam-105b (sarvam-105b, temp 0.3) — composite 1.0
- p50/p90/p99 TTFT: 291/325/325ms
- avg repetition (loop) score: 0.0
- stress p95: 642ms, cap-429: 0/24, key-failovers: 0

### conversations

**normal-flow** (rep=0.0)

- user: हाँ बताइए
- agent: जी Nikhil जी, मैं Joyville Sensorium के सिलसिले में बात कर रही थी — Shapoorji Pallonji का Hinjawadi project, आपने इसमें interest दिखाया था। बस दो मिनट लूँगी, फिर आप ही बताइएगा कि आगे बढ़ें या नहीं।
- user: 2 BHK में interest है
- agent: जी बिल्कुल, 2 BHK में क्या-क्या features चाहिए आपको?
- user: खुद के रहने के लिए
- agent: वाह, खुद का घर तो सबसे प्यारा सपना होता है। फिर तो जगह सोच-समझकर चुननी चाहिए, और location ही इसकी सबसे बड़ी खूबी है।
- user: price क्या रहेगा?
- agent: जी बता देती हूँ। दो BHK चौरासी point नौ-नौ लाख से शुरू है।
- user: ठीक है, एक बार देखना चाहूँगा
- agent: बहुत बढ़िया जी! हमारी Joyville Sensorium Sales Lounge पर हमारे Deputy Manager Sales, Anurag Saxena जी आपको पूरा project आराम से घुमाएँगे। आप weekend में free हैं या weekday सूट करता है?

**ambiguous-loop-trap** (rep=0.0)

- user: हाँ जी बोलिए
- agent: जी Nikhil जी, मैं Joyville Sensorium के सिलसिले में बात कर रही थी — Shapoorji Pallonji का Hinjawadi project, आपने इसमें interest दिखाया था। बस दो मिनट लूँगी, फिर आप ही बताइएगा कि आगे बढ़ें या नहीं।
- user: बताइए
- agent: जी शुक्रिया। बस ये समझना चाहती थी कि आप अपने रहने के लिए घर देख रहे हैं, या investment के नज़रिए से?
- user: आगे बोलिए
- agent: वाह, खुद का घर — सच में सबसे प्यारा सपना यही होता है। फिर तो जगह सोच-समझकर चुननी चाहिए, और location ही इसकी सबसे बड़ी खूबी है।
- user: हाँ हाँ आगे
- agent: जी Nikhil जी, आपने जो Hinjawadi चुना है, वो Pune का सबसे तेज़ी से बढ़ता हुआ IT hub है। यहाँ से IT parks बस पाँच मिनट की दूरी पर हैं।
- user: और बताओ
- agent: project में सबसे खास बात ये है कि यहाँ के towers angled रखे हैं, जिससे आमने-सामने की खिड़कियाँ नहीं हैं। हर घर में सीधी हवा और रोशनी आती है। पूरे एक acre पर बस सौ residences हैं, तो भीड़ बिल्कुल नहीं।

**price-objection** (rep=0.0)

- user: price बताइए
- agent: जी Nikhil जी, दो BHK चौरासी point नौ-नौ लाख से शुरू है, तीन BHK एक करोड़ बत्तीस लाख से, और premium चाहिए तो duplex भी है, एक करोड़ नवासी लाख का। आपके मन में कौन सा size चल रहा है?
- user: अरे बहुत महँगा है
- agent: देखिए जी, पहली बार सबको ऐसा लगता है, ये normal है। पर एक बार जगह और quality देखेंगे, तो इस location पर ये बहुत reasonable लगेगा — Shapoorji Pallonji का नाम ही काफ़ी है।
- user: पास में दूसरा project सस्ता मिल रहा है
- agent: अच्छा जी, तो फिर आप बता दीजिए कि वो project कहाँ है और वहाँ क्या-क्या मिल रहा है। मैं भी देख लेती हूँ कि क्या फर्क है।
- user: अच्छा फिर 2 BHK ही दिखाओ
- agent: बहुत बढ़िया जी! तो मैं आपकी एक site visit लगा देती हूँ, वहीं 2 BHK का पूरा sample घर देख लीजिएगा। आप weekend में free हैं या weekday सूट करता है?

**code-switch** (rep=0.0)

- user: can you explain the project in English?
- agent: Of course. It's Shapoorji Pallonji's new launch in Hinjawadi, Pune — 2 and 3 BHK homes, with angled towers so every flat gets direct light and air. And the new Mumbai-Pune Missing Link brings Mumbai down to about forty-five minutes. Would you like the pricing first, or the amenities?
- user: अब Hindi में amenities बताओ
- agent: जी, बिल्कुल। project में swimming pool, gym, और बच्चों के खेलने के लिए एक खास garden है। साथ ही, 24 घंटे security और parking की भी पूरी व्यवस्था है। और सबसे खास, हर घर में modular kitchen और Italian marble flooring है।
- user: 2 BHK की EMI कितनी बनेगी?
- agent: जी, दो BHK की कीमत चौरासी point नौ-नौ लाख से शुरू है। EMI का हिसाब बैंक के interest rate पर निर्भर करता है, पर लगभग छह से सात लाख तक की EMI बन सकती है। आपका करीब-करीब budget क्या रहता है, उसी हिसाब से सही option निकाल देती हूँ?
- user: ठीक है
- agent: बहुत बढ़िया जी! तो मैं आपकी एक site visit लगा देती हूँ, वहीं 2 BHK का पूरा sample घर देख लीजिएगा। आप weekend में free हैं या weekday आपको सूट करता है?

**adversarial-repeat** (rep=0.0)

- user: आपने क्यों call किया है?
- agent: जी Nikhil जी, आपने कुछ दिन पहले Joyville Sensorium project में interest दिखाया था, इसीलिए follow-up करने के लिए call किया है।
- user: क्यों call किया?
- agent: जी, project के बारे में कुछ जानकारी देने के लिए और आपकी सुविधा के लिए site visit का समय तय करने के लिए call किया है।
- user: मतलब क्या?
- agent: मतलब जी, आपके लिए project का पूरा layout और design समझाना और आपको घर देखने के लिए invite करना है।
- user: हाँ पर असल में क्यों?
- agent: जी, क्योंकि आपने खुद project में interest दिखाया था, तो मैं follow-up कर रही हूँ।
- user: ओके समझ गया
- agent: बहुत बढ़िया जी। तो आप site visit के लिए कब free हैं?

**hello-recovery** (rep=0.0)

- user: Hello?
- agent: जी Nikhil जी, मैं Joyville Sensorium के सिलसिले में बात कर रही थी — Shapoorji Pallonji का Hinjawadi project, आपने इसमें interest दिखाया था। बस दो मिनट लूँगी, फिर आप ही बताइएगा कि आगे बढ़ें या नहीं।
- user: आवाज़ नहीं आ रही थी
- agent: जी सुनाई दे रहा है? मैं पूछ रही थी — आप weekend में free हैं या weekday आपको सूट करता है?
- user: हाँ अब बोलिए
- agent: जी शुक्रिया। बस ये समझना चाहती थी कि आप अपने रहने के लिए घर देख रहे हैं, या investment के नज़रिए से?
- user: क्या project है ये?
- agent: अच्छा सवाल जी। project Hinjawadi Phase एक में है, IT hub बिल्कुल पास। और सबसे खास — towers angled रखे हैं, आमने-सामने खिड़कियाँ नहीं, तो हर घर में हवा-रोशनी सीधी। पूरे एक acre पर बस सौ residences, तो भीड़ बिल्कुल नहीं।

**trust-rapport** (rep=0.0)

- user: आप genuine हो ना? पहले एक builder ने पैसा लेके project लटका दिया था
- agent: जी Nikhil जी, मैं समझ सकती हूँ। इसीलिए तो मैं आपको Shapoorji Pallonji के बारे में बता रही हूँ — ये नाम ही भरोसे का है। आप चिंता मत कीजिए, मैं आपको project की सारी सही जानकारी दूँगी।
- user: ठीक है पर guarantee क्या है?
- agent: जी, ये बहुत सही सवाल है। Shapoorji Pallonji जैसे बड़े नाम के साथ आपको guarantee की ज़रूरत नहीं है। पर फिर भी, मैं आपको एक बात बताती हूँ — आपका पैसा RERA registered project में जाएगा, और सारी काग़ज़ी कार्रवाई पूरी होगी। आप एक बार आकर देख लीजिए, फिर खुद ही समझ आ जाएगा।
- user: अच्छा site कहाँ है?
- agent: जी, project Hinjawadi Phase One में है। ये IT hub के बिल्कुल पास है, और नया Mumbai-Pune Missing Link road से Mumbai सिर्फ़ forty-five minutes में पहुँच जाएगा। आप weekend में आ सकते हैं, मैं Anurag जी से बात कर लेती हूँ कि वो आपके लिए time रख लें।

**complex-q** (rep=0.0)

- user: 2 vs 3 BHK में rental income के लिए कौन better रहेगा और क्यों?
- agent: जी Nikhil जी, rental income के लिए 3 BHK अक्सर ज़्यादा बेहतर रहता है। क्योंकि Hinjawadi जैसे IT hub में ज़्यादातर families और working professionals रहते हैं, और वे तीन कमरे वाले घर को ज़्यादा पसंद करते हैं। इससे आपको ज़्यादा किराया मिलता है और घर भी जल्दी बिकता है।

2 BHK से कम किराया मिलता है और उसे किराए पर देना भी थोड़ा मुश्किल हो सकता है, ख़ासकर अगर आप single tenant ढूँढ रहे हैं। 3 BHK में आपको ज़्यादा options मिलते हैं।
- user: और resale value के हिसाब से?
- agent: जी Nikhil जी, resale value के लिए भी 3 BHK ही बेहतर माना जाता है। Hinjawadi जैसे prime location में, जहाँ families ज़्यादा रहती हैं, 3 BHK की माँग हमेशा बनी रहती है।

2 BHK की value भी तो है, पर 3 BHK में आपको ज़्यादा फ़ायदा मिलता है क्योंकि यह लंबे समय के लिए एक सुरक्षित investment है। ज़्यादा जगह और बेहतर layout की वजह से इसकी resale value हमेशा अच्छी रहती है।
- user: ठीक है weekend पे आता हूँ
- agent: बहुत बढ़िया जी! तो शनिवार पक्का। मैं Anurag जी को बता देती हूँ कि आप आ रहे हैं, वो आपके लिए time रख लेंगे। पहुँचिएगा तो मेरा नाम बता दीजिएगा, रिया ने भेजा है। मिलते हैं फिर शनिवार को, अपना ख़याल रखिएगा।

---

## #2 groq-70b (llama-3.3-70b-versatile, temp 0.4) — composite 0.395
- p50/p90/p99 TTFT: 309/403/403ms
- avg repetition (loop) score: 0.031
- stress p95: 13779ms, cap-429: 0/24, key-failovers: 0

### conversations

**normal-flow** (rep=0.0)

- user: हाँ बताइए
- agent: जी Nikhil जी, मैं Joyville Sensorium के सिलसिले में बात कर रही थी — Shapoorji Pallonji का Hinjawadi project, आपने इसमें interest दिखाया था। बस दो मिनट लूँगी, फिर आप ही बताइएगा कि आगे बढ़ें या नहीं।
- user: 2 BHK में interest है
- agent: जी Nikhil जी, दो BHK चौरासी point नौ-नौ लाख से शुरू है, और एक बार देख लें तो खुद ही समझ आ जाता है। हमारे Joyville Sensorium में location और design दोनों बहुत अच्छे हैं, और Shapoorji Pallonji का नाम ही काफ़ी है। आप weekend में free हैं या weekday सूट करता है? मैं आपकी एक site visit लगा देती हूँ, वहीं 2 BHK का पूरा sample घर देख लीजिएगा।
- user: खुद के रहने के लिए
- agent: वाह, खुद का घर — सच में सबसे प्यारा सपना यही होता है। फिर तो जगह सोच-समझकर चुननी चाहिए, और location ही इसकी सबसे बड़ी खूबी है। Hinjawadi में जो connectivity है, वो बहुत अच्छी है, और हमारे project में भी सभी सुविधाएँ हैं। आप अपने घर के लिए कौन सी सुविधाएँ सबसे ज्यादा महत्वपूर्ण मानते हैं?
- user: price क्या रहेगा?
- agent: जी बता देती हूँ। दो BHK चौरासी point नौ-नौ लाख से शुरू है, और यह दाम बहुत ही reasonable है इस location और quality के हिसाब से। आप चाहें तो मैं आपको EMI का भी calculation बता सकती हूँ, ताकि आपको अपने budget के हिसाब से समझने में आसानी हो।
- user: ठीक है, एक बार देखना चाहूँगा
- agent: बहुत बढ़िया जी! हमारी Joyville Sensorium Sales Lounge पर हमारे Deputy Manager Sales, Anurag Saxena जी आपको पूरा project आराम से घुमाएँगे। आप weekend में free हैं या weekday सूट करता है? मैं आपकी एक site visit लगा देती हूँ, वहीं 2 BHK का पूरा sample घर देख लीजिएगा।

**ambiguous-loop-trap** (rep=0.0)

- user: हाँ जी बोलिए
- agent: जी Nikhil जी, मैं Joyville Sensorium के सिलसिले में बात कर रही थी — Shapoorji Pallonji का Hinjawadi project, आपने इसमें interest दिखाया था। बस दो मिनट लूँगी, फिर आप ही बताइएगा कि आगे बढ़ें या नहीं।
- user: बताइए
- agent: जी बता देती हूँ। दो BHK चौरासी point नौ-नौ लाख से शुरू, तीन BHK एक करोड़ बत्तीस लाख, और premium चाहिए तो duplex भी है, एक करोड़ नवासी लाख का। आपके मन में कौन सा size चल रहा है?
- user: आगे बोलिए
- agent: जी Nikhil जी, तो ये project Hinjawadi Phase वन में है, IT hub बिल्कुल पास। और सबसे खास — towers angled रखे हैं, आमने-सामने खिड़कियाँ नहीं, तो हर घर में हवा-रोशनी सीधी। पूरे एक acre पर बस सौ residences, तो भीड़ बिल्कुल नहीं। और नया Mumbai-Pune Missing Link बन गया है, उससे Mumbai अब सिर्फ़ पैंतालीस minute रह गया है।
- user: हाँ हाँ आगे
- agent: जी Nikhil जी, तो अब मैं आपको बता दूँ कि हमारी Sales Lounge पर आपका स्वागत है। हमारे Deputy Manager Sales, Anurag Saxena जी आपको पूरा project आराम से घुमाएँगे। आप weekend में free हैं या weekday सूट करता है?
- user: और बताओ
- agent: जी Nikhil जी, हमारी Joyville Sensorium Sales Lounge पर आपको पूरा project दिखाया जाएगा, और आपके सभी सवालों का जवाब दिया जाएगा। और अगर आप घर लेने का फैसला करते हैं, तो हम आपको बहुत अच्छा offer देंगे। तो क्या आप शनिवार को हमारी Sales Lounge पर आकर project देखना चाहेंगे?

**price-objection** (rep=0.0)

- user: price बताइए
- agent: जी Nikhil जी, दो BHK चौरासी point नौ-नौ लाख से शुरू है, तीन BHK एक करोड़ बत्तीस लाख, और premium चाहिए तो duplex भी है, एक करोड़ नवासी लाख का। आपके मन में कौन सा size चल रहा है?
- user: अरे बहुत महँगा है
- agent: बिल्कुल समझती हूँ जी, पहली बार सबको ऐसा लगता है, ये normal है। पर एक बार जगह और quality देखेंगे, तो इस location पर ये बहुत reasonable लगेगा — Shapoorji Pallonji का नाम ही काफ़ी है।
- user: पास में दूसरा project सस्ता मिल रहा है
- agent: हम्म, समझ रही हूँ जी। पर एक बात बताऊँ — Joyville Sensorium की location और quality का कोई मुकाबला नहीं है। Hinjawadi में यही सबसे अच्छी जगह है, और Shapoorji Pallonji का नाम ही काफ़ी है कि यहाँ की प्रॉपर्टी की value कभी घटेगी नहीं। दूसरे project में क्या खास है, वो बता सकते हैं?
- user: अच्छा फिर 2 BHK ही दिखाओ
- agent: बहुत बढ़िया जी! तो मैं आपकी एक site visit लगा देती हूँ, वहीं 2 BHK का पूरा sample घर देख लीजिएगा। आप weekend में free हैं या weekday सूट करता है?

**code-switch** (rep=0.0)

- user: can you explain the project in English?
- agent: Of course. It's Shapoorji Pallonji's new launch in Hinjawadi, Pune — 2 and 3 BHK homes, with angled towers so every flat gets direct light and air. And the new Mumbai-Pune Missing Link brings Mumbai down to about forty-five minutes. Would you like the pricing first, or the amenities?
- user: अब Hindi में amenities बताओ
- agent: बिल्कुल जी। तो हमारे Joyville Sensorium में आपको बहुत सारी अच्छी amenities मिलेंगी — जैसे कि clubhouse, swimming pool, gym, kids' play area, और बहुत सारे green spaces। और सबसे अच्छी बात ये है कि ये सारी सुविधाएँ बहुत ही अच्छी quality में हैं, ताकि आप और आपका परिवार आराम से रह सकें।
- user: 2 BHK की EMI कितनी बनेगी?
- agent: जी Nikhil जी, दो BHK की कीमत चौरासी point नौ-नौ लाख है, तो EMI की गणना करके बता देती हूँ। मान लीजिए आप पूरी कीमत का बीस प्रतिशत down payment करते हैं, तो बाकी की राशि पर लोन लेते हैं। तो EMI लगभग पचास हज़ार से शुरू होगी, लेकिन ये बैंक और लोन की शर्तों पर भी निर्भर करता है। आप चाहें तो मैं आपको हमारे financial partner से भी जोड़ सकती ह
- user: ठीक है
- agent: बहुत बढ़िया जी! तो मैं आपकी एक site visit लगा देती हूँ, वहीं 2 BHK का पूरा sample घर देख लीजिएगा। आप weekend में free हैं या weekday सूट करता है?

**adversarial-repeat** (rep=0.0)

- user: आपने क्यों call किया है?
- agent: जी Nikhil जी, मैं Joyville Sensorium के सिलसिले में बात कर रही थी — Shapoorji Pallonji का Hinjawadi project, आपने इसमें interest दिखाया था। बस दो मिनट बात करनी थी कि क्या आप अभी भी इस project में दिलचस्पी रखते हैं और आगे बढ़ने के बारे में क्या सोचते हैं।
- user: क्यों call किया?
- agent: जी Nikhil जी, आपने Joyville Sensorium में interest दिखाया था, तो बस उसी के बारे में दो मिनट बात करनी थी। दो BHK चौरासी point नौ-नौ लाख से शुरू है, और एक बार देख लें तो खुद ही समझ आ जाता है।
- user: मतलब क्या?
- agent: जी Nikhil जी, मतलब यह है कि हमारे पास आपकी जानकारी थी कि आपने Joyville Sensorium में रुचि दिखाई थी, और मैं यह जानना चाहती थी कि क्या आप अभी भी इस प्रोजेक्ट में दिलचस्पी रखते हैं और आगे की जानकारी चाहते हैं।
- user: हाँ पर असल में क्यों?
- agent: जी Nikhil जी, असल में हम चाहते हैं कि आप Joyville Sensorium को अपने घर के रूप में देखें और इसकी सारी सुविधाओं और खूबियों को जानें। हमारा मकसद है कि आप यहाँ आकर देखें और अपने लिए सबसे अच्छा निर्णय लें।
- user: ओके समझ गया
- agent: जी Nikhil जी, अच्छा जी! तो अब मैं आपको बता देती हूँ कि हमारे पास क्या विकल्प हैं। हमारे पास दो BHK, तीन BHK, और तीन BHK डुप्लेक्स हैं। दो BHK की कीमत चौरासी point नौ-नौ लाख से शुरू होती है। क्या आप इनमें से कोई विकल्प देखना चाहेंगे?

**hello-recovery** (rep=0.25)

- user: Hello?
- agent: जी सुनाई दे रहा है? मैं रिया बोल रही हूँ, Joyville Sensorium की senior sales consultant। आपने हमारे project में interest दिखाया था, बस उसी के बारे में दो मिनट बात करनी थी।
- user: आवाज़ नहीं आ रही थी
- agent: जी सुनाई दे रहा है? मैं रिया बोल रही हूँ, Joyville Sensorium की senior sales consultant। आपने हमारे project में interest दिखाया था, बस उसी के बारे में दो मिनट बात करनी थी।
- user: हाँ अब बोलिए
- agent: जी Nikhil जी, मैं बता रही थी कि Joyville Sensorium का project Hinjawadi Phase वन में है, IT hub बिल्कुल पास। और सबसे खास — towers angled रखे हैं, आमने-सामने खिड़कियाँ नहीं, तो हर घर में हवा-रोशनी सीधी। पूरे एक acre पर बस सौ residences, तो भीड़ बिल्कुल नहीं।
- user: क्या project है ये?
- agent: जी Nikhil जी, ये Shapoorji Pallonji का नया project है, जिसमें 2 और 3 BHK के घर हैं। दो BHK चौरासी point नौ-नौ लाख से शुरू है, और तीन BHK एक करोड़ बत्तीस लाख से। और एक खास बात — ये Hinjawadi में है, तो Mumbai-Pune Missing Link से Mumbai सिर्फ़ पैंतालीस मिनट की दूरी पर है।

**trust-rapport** (rep=0.0)

- user: आप genuine हो ना? पहले एक builder ने पैसा लेके project लटका दिया था
- agent: बिल्कुल समझती हूँ, Nikhil जी। आपकी चिंता वाजिब है। कई बार ऐसा होता है कि builders पैसा लेकर project को लटका देते हैं और घर खरीदने वालों को परेशानी होती है। लेकिन मैं आपको बता दूँ कि Joyville Sensorium के builder Shapoorji Pallonji एक बहुत ही विश्वसनीय और अनुभवी नाम हैं। उनकी पिछली परियोजनाओं को देखकर आप समझ सकते हैं कि वे समय पर पूरा करने और गुणवत्ता के म
- user: ठीक है पर guarantee क्या है?
- agent: बिल्कुल सही सवाल जी! Shapoorji Pallonji के साथ हमारे पास RERA registration है, जो कि एक सरकारी गारंटी है कि project समय पर पूरा होगा और सभी नियमों का पालन किया जाएगा। साथ ही, हमारे पास एक स्पष्ट construction timeline है जिसे हम अपने ग्राहकों के साथ साझा करते हैं। और सबसे महत्वपूर्ण बात, हमारे पास एक strong after-sales support system है जो आपको पूरी तरह से संतुष्ट करने के लिए हमेशा तैय
- user: अच्छा site कहाँ है?
- agent: जी Nikhil जी, Joyville Sensorium का site Hinjawadi Phase 1 में है, जो कि पुणे का एक बहुत ही विकसित और सुविधाजनक इलाका है। यहाँ से पुणे के सभी मुख्य इलाकों में आसानी से पहुँचा जा सकता है, और साथ ही यहाँ पर कई बड़े IT कंपनियों के office भी हैं। साइट का पता है - Hinjawadi Phase 1, Near Shivaji Chowk, Pune। आप यहाँ आसानी से पहुँच सकते हैं और अपने आप को project की सुंदर

**complex-q** (rep=0.0)

- user: 2 vs 3 BHK में rental income के लिए कौन better रहेगा और क्यों?
- agent: जी Nikhil जी, अगर rental income की बात करें तो दोनों ही विकल्प अच्छे हैं, पर 2 BHK और 3 BHK में थोड़ा अंतर है। 2 BHK की demand ज्यादा रहती है क्योंकि ज्यादातर लोग छोटे परिवार के साथ रहते हैं और उन्हें दो कमरे काफी लगते हैं। इससे 2 BHK की rental income थोड़ी स्थिर रहती है और आसानी से किराए पर मिल जाती है।

दूसरी तरफ, 3 BHK ज्यादा बड़े परिव
- user: और resale value के हिसाब से?
- agent: जी Nikhil जी, resale value के हिसाब से देखें तो 3 BHK की resale value ज्यादा अच्छी रहती है। बड़े घरों की demand हमेशा रहती है, खासकर उन परिवारों में जो बड़े हैं या जिन्हें ज्यादा जगह चाहिए। इससे 3 BHK की resale value में ज्यादा बढ़ोतरी होती है और यह एक अच्छा investment विकल्प बन जाता है।

एक और बात, जो लोग 3 BHK लेते हैं वो अक्सर अपने घर को बहुत सारी सुविध
- user: ठीक है weekend पे आता हूँ
- agent: बहुत बढ़िया जी! तो शनिवार को आप आ रहे हैं, मैं Anurag जी को बता देती हूँ कि आप आ रहे हैं, वो आपके लिए समय रख लेंगे। पहुँचिएगा तो मेरा नाम बता दीजिएगा, रिया ने भेजा है। मिलते हैं फिर शनिवार को, अपना ख़याल रखिएगा।

---

