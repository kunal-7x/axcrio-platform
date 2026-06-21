 
# you asked

There are a few more problems. For example, the problems are like currently the particular callback, like actually, that is the callback, sorry, the recording is not working. That's what you already know, that's the biggest one. I need instant recording first thing. Fuck you. Whatever I tell you, summarize everything in one paragraph. summarize everything in one paragraph. In the one headline. One text in one paragraph.

---

# chatgpt response

**Recording is currently not working, which is the highest-priority issue and needs to be fixed first by enabling instant recording; additionally, any callback-related functionality should be reviewed and verified since there appears to be a problem there as well, with the immediate focus being to ensure recording starts instantly and functions reliably before addressing other issues.**

---

# you asked

So first thing is like whatever vendor scripts that you have given me, for example, in the campaign, I have an option called script. I put a vendor script, but actually when I run that, it is speaking the same thing. Actually in that, for example, in the vendor script, I told that first you tell hello sir, mam, good morning or good afternoon according to the time. Once that done, then it greets from the whatever that particular campaign that we are running. For example, I am speaking from Serapoonji real estate. Then he just asks, I am speaking to the Mr. Kunal or whatever name. First wait for the confirmation. Then he told about, hey, I'm going to talk about upcoming registration project and so on and so forth. I put that kind of script, but actually not working. Second thing is like the render brain, the render brain. I don't, why you, see, maybe there is need of that much bit script. And first thing, the biggest bug that I find out, I actually submitted a very lot of detail about the campaign, but it is compressing everything and finding few things. What the fuck that is. Means this don't have any kind of context about the campaign. I have submitted a lot of detail in the campaign brief. It should have all of those details. For that, they actually do the objection handling and give the any answer. Why you have hard-coded in, I can campaign brief when you expect fill in the JSON form. I can able to see why you have fucked, you fucked the 2 to 3 objection handling. Why you have fucked that, maybe that worked, maybe that don't work. Don't just put the 2 or 2 or 3 objection handling. That even, as even putting in the system prompt, that didn't even make sense. In the system prompt, we need that particular behavior and the biggest thing would be the getting the whatever user submitted details about that particular campaign. That's all the more detail. That are not too much detail. That is around less than one page or like 2 to 3,000 characters. That's enough. We should have to put entire detail in that. So that AI should have the full context. If it actually needs more and more, it will see the other retrieval document system. This current abstracted field is broken. First thing, it has a 2 to 3 objects in handling. It's just listing the input token. There is no need because there is no sense. Second thing, it's like you have to abstract the field, but try to get the entire context whatever user have submitted because the more the context we have, more the good answers that we can able to do. Never ever hard code the way we speak. Few more things, I said current system that what we have built, it have its predefined how to speak, how to do and whatever username that are dynamic value. I agree that no worry about that, but hard coding at the max depth becoming problem and jargon. Sometime it speak half word and stop. Means like it always speak the perfect word. For example, sometime it didn't speak the last word. For example, main aapke liye yeh cheez batana chahati, then who it didn't speak. It speak main aapko batana chahati and then he didn't speak who. And he's speaking too much Hindi word. For example, there is no sense. He asked me like yeh project aapke liye kitna mahatvapurn hai. What kind of this fucking sentence it is? It should be the real human. And why you are asking like mahatvapurn? You should ask like, sir, aapke liye yeh project aapko sahi lag raha hai aapke use case ke liye something like that kind of question they should ask. See, I thought your entire prompting system, the voice layer that you have built, the system form that you have built where you would predefined, hard coded a lot of things. I can able to see whenever you are putting every response that you got that have the 8,000 tokens, 8,000 tokens on every message. That are a lot of tokens. You did both with that, but you are literally instead of defining the behavior, object handling, and something like that, you fucking idiot, what you have did it? Instead of the code thing, it should have the most of the campaign, how does it? You have don't hardcode the response because AI, today AI, our model is so capable, how to speak, how to give the response, why are we hardcoding? And we have one called vendor script, where I can put the vendor script, how to speak, like introduction, like should be like this, after introduction, greet from our whatever history, then ask their name, then tell us more about, then tell more projects, and so and so forth. They are scripts. That also goes, so they exactly get to know how to speak. If we are hardcoding, if we are hardcoding this, how to escape, how to that it, so and so forth, that's fucking so idiotic, and that really makes sense at all, that we have to work on this particular thing, okay. So this thing, the core brain, I thought we have hardcoded everything in our core brain, hardcoding everything. Yes, whatever name that they have, they should speak with and greet with that. It should know that I have the entire context what project they are working on. That's perfect. But I thought we have hardcoded so much. See, maybe I am right, maybe I am wrong. What could be the best possible thing? See, also, as a project details, and see, we have to use three layers, one called Postgres, where user ID and everything, main campaign, and whatever. Then one is like Redis caching for the, before call actually happens, we have to load everything. I thought it is wrong. And like one is called Redis, after that, retrieve the document system. And one biggest thing called system prompt. Currently, you are giving lot of thing. You have 20,000 system prompt characters. It is too much. Like... Not too much. I am agreeing with that. Whatever you are going to give it, that's perfect. I am not saying or something like that. That's perfect.

---

# chatgpt response

**The current voice-agent architecture is over-hardcoded and is causing multiple failures: vendor scripts are being ignored so the agent does not follow the user-defined conversation flow (greeting based on time, introducing the company, confirming the prospect's identity, then presenting the project), campaign briefs are being aggressively compressed into a few extracted fields which removes critical context needed for objection handling and accurate responses, objection handling has been artificially limited to a few predefined entries instead of leveraging the full campaign knowledge, and too much conversational behavior is being dictated by the core prompt instead of allowing the LLM to naturally generate responses from campaign context and vendor scripts. The system should prioritize loading complete campaign information (2–3k characters or more if available) from Postgres into Redis before the call, provide that full context to the model, use retrieval only as a secondary source for deeper knowledge, and keep the system prompt focused on behavior, guardrails, and conversation quality rather than campaign content. The agent should never hardcode exact phrasing, should speak naturally like a real human, avoid unnatural Hindi such as ‘mahatvapurn,’ stop truncating words or sentences midway, respect the vendor-defined conversation structure, maintain awareness of the entire project context, and dynamically answer objections using campaign knowledge rather than a small predefined list. The overall goal is to move from a rigid prompt-driven agent to a context-driven agent where campaign data and vendor scripts control what is said, while the system prompt only controls how the AI behaves and speaks.**

---

# you asked

I have seen your system from the Renderbrain. I have no problem that have 15,000 characters. That is actually so good and actually train the model perfectly. The only problem that we have, are we hard-coded something in our system because Renderbrain is perfect. Renderbrain is perfect. But why have we have hard-coded a lot of things? The vendor script is actually not working. Whatever vendor script that I'm putting, that is also not working. Okay. And in the Renderbrain, please make sure whatever user submitted the campaign, in the campaign brief box, whatever user submitted about the campaign data, it should get the entire rich context, all context, so that it gives the perfect answer and have everything, okay? And I don't know why your objection handling or everything that you have created in the, I don't know, knowledge base or wherever, that actually working or not. I am fucking shit. I don't know actually working or not. Means that should work in the real time also, okay? I can put a lot of objection handling, how to objection handle and so and so forth. That should work in the real time also, okay, perfectly. Your Renderbrain is perfect. I am telling again, perfect. You can improve more if you want. One more thing, I don't know your knowledge base actually working in real time if I put a PDF. For example, I have a campaign. I put an entire PDF of that particular campaign. If user asks more deep questions and he didn't get in the system from somewhere, it should fetch those PDFs or through the retrievable document vector embedding, like what we have it, PG vector or so fast in the literally zero millisecond or 10 millisecond, low complete low latency, whatever. I don't care shit. Fuck that. It's already have built the one more fucking shit of the thing that I need to tell and most of the entire system, entire thing, like vector database. And all things are already built it. I just want to know if it's actually working or not. Biggest bug currently at this point in time is the human handoff. That's actually not working. Make sure human handoff works and it don't... See, current human handoff scenario is if user asks, I really want to call to your team lead, I really want to buy, it really transfers the call. And see, the handoff is not currently working. It's not even playing the music. It's not even ringing on the other mobile. That's handoff system is also broken. So you have to work hard on this so that it works seamlessly. If user asks, can you call me your team lead? Without any explanation, without anything that I'm transferring the call, hold, or nothing, fuck that, fuck, fuck, fuck. Just do one thing. Okay, sir, I am transferring the call to my team. That's it. No more than that. Not saying the phone number, nothing, nothing, nothing. And then just call a music that we already have in that play and call transfer in the same SIP room. That's the fuck that. That's the thing where that we need it, not more than that. Okay? Fuck you.

---

# chatgpt response

**RenderBrain itself is not the problem and can remain large (15,000+ characters) because it properly trains behavior and conversation quality; the real issues are that too much conversation logic appears to be hardcoded, vendor scripts are not being followed, and campaign context is being reduced instead of fully utilized. The vendor script must have the highest priority for conversation flow so the AI follows the exact introduction, greeting, identity confirmation, and pitch sequence defined by the user. The campaign brief should be passed with maximum fidelity, preserving all submitted details rather than compressing them into a few abstract fields, allowing the AI to use the full campaign context for responses and objection handling. Objection handling and knowledge-base content must work dynamically at runtime, not as a limited predefined list, and uploaded PDFs or documents should be retrievable through the existing vector database and retrieval system whenever deeper campaign-specific questions are asked. The system prompt should focus on behavior, guardrails, and conversation quality, while campaign details, vendor scripts, and retrieved knowledge drive the actual content of responses. Additionally, the human handoff flow is currently broken and must reliably transfer calls when requested, playing hold music and connecting the recipient within the same SIP flow; the AI should simply acknowledge the transfer with a short confirmation and immediately initiate the handoff process without extra explanations, phone numbers, or unnecessary dialogue.**

---

# you asked

One more bug I thought in your system prompt you have deleted. Please, please, please, is never ever say I am speaking an AI assistant. I have told you three times, you said you and you resolved and then you say, Hey, I am done. But every time when I get the call, it is still speak I am AI assistant. It shouldn't speak. It should skip with my script. Vendor script or whatever. The first thing would be the like, if there is a vendor script, it should be go with that. LLM should learn according to the vendor script how should I speak and all this stuff. As we have to, if no script, we have that system going to be speak with our, what we have. The current, what we have in our code system that completely broken at its core, at its foundation. It should first greet. I will share one, you know, vendor script. Okay, I will share one vendor script so you get to know. That is the not even a, that actually what actually I am telling you. That actually, if you know that they are the real human telecaller, okay, in the real life, real human telecaller also get a script. They get some direction how to speak, how to behave and so and so forth. So I get it underneath a secret, secret of those, how actually they speak. So instead of searching on the internet and everything and wasting your computation, I get you a pre-made meal, so you have to just get to know what it is. And also, also like that have also a project detail, so don't hardcode those project details. Please, please, please, in the brain don't hardcode those project details. I have shared one vendor script, so make sure that in future AI should speak greet, something like that. And don't hardcode any vendor detail. It should be the dynamic according to the whatever campaign that we are running, whatever username, whatever property detail, whatever that user have submitted inside the campaign, that should be the dynamically changed. Okay, that we currently already have. I am just reminding you, so that don't hardcode anything. This is just a example vendor script. Example vendor script of a one particular specific campaign. Okay, because you have that particular, I have shared because you get to know how to now you have to build your AI brain, how you should have to build your AI brain so that it should work like that. Okay, I really want to test. I can give you the brief. You already know it should take just entire instruction for one telecaller, because that's for the real telecaller, and that's now how we actually, because we are actually building the real telecaller and that we have to AI assistant, so do like. So it's tell that introduction should happen, hello sir, ma'am, good evening, then greeting from Sirapunji, whatever. So it means like greeting, it should generate a greeting from whatever campaign that we are running. Then it asks their name, I am speaking to sir, wait for confirmation, and it also registered. If obviously, if the outbound call, if he knows the name, obviously he's known the name, that's why he's asking. And then calling and something that I already shared. If you see the, read that particular script, please put something in our system, that kind of script. Don't hardcode because that is the one specific campaign, so in future, it dynamically changes whenever any call goes to according to whatever X campaign that we are running. Also, it also dynamically changes if the user submitted their predefined vendor scripts, then also that override the other. Getting the content. See, now, the thing is like, but I don't, I know, no one going to put the vendor script, so use your entire computation, use your entire reasoning, run at least three to five sub-agents. So that what should be the possible best transcripts. I have shared with you, you do also web search, deep search, how real telecaller speak in the real caller, how they ask questions, everything. End-to-end, and you have to put in our system prompt. I don't know, because I am new and beginner. I don't know where you have to put it. It could be in the system prompt. It could be in the retrievable argument system. It could be in the Redis for the caching, for instance, hot caching, fast caching, or like getting the instant data. I don't know, fuck that. It could be in the system prompt or whatever, I don't know. See, I don't care a shit. You have to take the call. Take the call. Don't hard code anything. First thing, that's the biggest bug. If you hard coding any response, if you speak this line, that also, getting the context. So see, I don't care a shit. Use your entire computation reasoning in building something so perfect for that you obviously run multiple sub-agents for the exploring the first service. I don't care a fucking shit. Run any number of, any number of sub-agents, any number of, at least exploring should be at least 15 agents. They will explore and diagnose this entire problem of the how AI is speak. I have also shared some scripts. You also do the web search. What could be the best optimal way? How it's speak, greet, uh, ask the name, then how actually it say the property, what kind of question it asks, and so and so forth. Getting the context, it should be so perfect, perfect, perfect. And please, please, please, whenever I, vendor is actually putting their campaign detail in the campaign brief, I know they convert into the JSON so compressed form and it loses the entire context. When you actually put those in the uh the system prompt, what I want. Can you, because that is not too much big campaign details. So, please try to, whatever user has submitted, try to get the entire context to the AI or the system prompt or whatever, so that he actually have a greater context of the entire knowledge about that particular property and everything, so that he can handle all the things, all the things, directly, instantly that who actually need it and that you shouldn't focus on that particular thing. And please, this is the English script, okay, one thing. Uh, for, it should, if the Hindi, it should be the Hindi. Getting the Hinglish, Hinglish. You already know that adaptive, that what we have built it. If a user is asking in Hindi, it should speak in Hindi. If user in the next response, uh, asking you speak in English, AI should speak in English. If in the very next response speak in Hindi again, it should respond in the Hindi again. With the entire context and everything, so crazy level, so that it have the, it's the perfect thing that we could have it. User will try to submit everything in the campaign brief, try to submit everything, and try to get the entire context. Don't compress in the JSON form. It's end, don't put hard-coded one to two objection handling, that fucking shit, okay? Just don't do that. Try to get the entire campaign detail and whatever. Try to, try to get the entire context, end to end, okay? Because, from whatever you submitted and there, so that AI can able to get to know everything, everything, everything. One more thing, your current uh brain, the system brain, the render brain, that is perfect. Don't, I don't care if it is a too much token. Uh, that's perfect, don't worry about that. Use your entire computation and reasoning. And also, once you're done with the exploring this, uh, map out all the things, where we are broken the system, where we hard-coded everything, don't hard-code anything. And I am not saying you to, you also take blindly and take the decision. You take the call. What do you actually think? Should we need to hard-code? Should we need to dynamic? Should we need to adaptive intelligence according to the whatever that we have it? Explore and map all the things, and could be whatever, I don't care a shit. Then come up with the complete research, web search, and everything completely. Then diagnose at the max depth. Then after that, obviously research, diagnose at the max depth. Then a biggest, biggest, a very big red team come. Red team, you already know that we run by obviously Opus. Red team will change the entire game. And then, obviously, red team do everything perfect. Then obviously design and plan and everything. Then, without moving to the another workflow, on the same workflow, you'll try to build the entire brain or whatever, the backend, front-end, could be whatever, you will edit, build it. Then it means like implementation and build. Then after that, verify and deploy and everything and live test and everything all done, perfect. Also means like never ever from scratch, zero to everything, do it in the one go, one ultra workflow, end-to-end, no matter how much, at each phase should be have the 15 agents, please, please, please, please, please. Each phase have 15 agents because we need complete diagnose. We need complete solution. Whatever I tell is just 1%. I am noob, I am beginner, I cannot tell everything. You have to take the call. You have to take the call. Your goal is to make the real human telecaller, this entire system. Your goal is to make the real human telecaller system. The things that I have made, tell to you, the problem that I have told to you, the solution that I have told to you, that is just 1% of problem, 1% solution in which we are going to face 99% of problem and we need 99% solution. That's I don't know, but and you also blind spot, I also blind spot. You have to go web, deep thing, deep, think harder. What kind of something that we actually need in our system. Because that 99% completely blind spotted, and we have to figure it out. You are going to figure it out. You run another phase before the red team called completely blind spotted thing, and out of the box, something. Then red team and everything, whatever 99% thing that we have missed it, you will add all of those things. Maybe the entire architecture is also not. Maybe not the entire architecture, the current architecture, the way that we are actually using, that also wrong. Maybe the, we need that particular, maybe we have those system or not, and maybe the Redis or the fast forward caching or retrieval augumentation system from this put the entire architecture completely wrong way, structured wrongly wired. I don't care, fuck that, fuck that, fuck that, fuck everything. I need the entire system so crazy, working so perfect, so perfect, so perfect. So that's all about it. Use your entire computation and see, I don't care a shit. Use entire reasoning, entire reasoning. I don't care a shit, like whatever campaign brief should convert in the JSON or put the entire detail, whatever I have user submitted in the entirely directly in the JSON, directly in the rendered brain or it convert in the JSON. I don't care a shit. Whatever you take the call. See, the core thing is not making LLM freely. It's the scripts. If you really know the vendors, they give their... They give their script to the telecaller. Telecaller actually follow those scripts, okay? Because the telecaller follow those scripts. So like we have to also copy that method. I have shared one script. You can also go on the website, do whatever, find out multiple scripts, and could be whatever, train our AI brain. How to speak, how to behave, and everything. I have shared one script. And I also dynamic. We have the vendor script option while we have the... In the campaign, we can edit the vendor script. So if the vendor is also submitted from their site, that also should be adaptive and that should also behave according to that also. Perfect. See, use the entire computation. I don't care a shit. Entire computation. And be genuinely so crazy, because please, please note an attention on this word. The entire, entire message that I told you, the biggest thing is this line below. Listen, whatever I tell to you, it could be the problem, solution, whatever, it's just 1%. Other 99%, you blind spotted, me also blind spotted. Now your goal, find out all the 99% of problems, solutions, everything, build those, add to our system, and make the system perfectly 100% perfect.

---

# chatgpt response

**The AI calling system should be redesigned around a dynamic, context-driven telecaller architecture rather than a hardcoded conversational architecture. The agent must never introduce itself as an AI assistant, must prioritize and strictly follow the vendor script whenever one is provided, and only fall back to the default conversation framework when no vendor script exists. Vendor scripts should act as conversation blueprints that define greeting, identity confirmation, discovery, pitch, qualification, objection handling, and closing flow, while all campaign-specific information remains fully dynamic based on campaign data. The campaign brief should not be aggressively compressed into a few JSON fields because that removes critical context; instead, the system should preserve and inject as much campaign context as possible so the model has complete knowledge of the property, offer, company, FAQs, differentiators, and sales information. Objection handling should not be limited to a small predefined list and must leverage the full campaign brief, uploaded documents, knowledge base, and retrieval system in real time. The knowledge base and vector retrieval layer must reliably fetch information from uploaded PDFs and campaign documents whenever deeper questions are asked, ensuring low-latency access to campaign-specific details. RenderBrain itself is not the issue and can remain large because it successfully governs behavior; however, it should focus on agent behavior, tone, guardrails, conversation quality, language adaptation, and call objectives rather than hardcoded campaign content or scripted responses. The system should dynamically adapt between Hindi, Hinglish, and English based on the prospect’s most recent utterance, use natural human telecaller language rather than artificial phrasing, avoid truncated words and incomplete sentences, and generate responses naturally from context rather than predefined text. Architecturally, campaign data should be loaded from the primary datastore, cached before call initiation, combined with runtime retrieval from the knowledge base, and supplied to the model as rich context rather than compressed summaries whenever possible. The human handoff flow must function reliably by detecting transfer intent, acknowledging the request briefly, initiating hold music, and seamlessly connecting the call within the existing telephony flow. More broadly, the system should be evaluated end-to-end to identify hidden assumptions, over-hardcoded behaviors, context-loss issues, retrieval failures, prompt conflicts, latency bottlenecks, language-quality issues, telephony integration problems, and conversation-design flaws, with the goal of creating an AI telecaller that behaves like a highly trained human sales agent: guided by dynamic scripts, fully aware of campaign context, capable of natural conversation, able to answer deep questions from campaign knowledge, adaptive to user language, and free from rigid hardcoded conversational behavior.**

---

# you asked

The current campaign brief, whenever it extracts the field, its the system is broken. It's broken old. Whenever I try to build this for the particular first time, when I build and you never ever updated it, it's broken. Entirely rebuilt it from scratch. Okay. It's like, whenever I get the windy script, it's just converting into a small JSON. Fuck that, it's losing the entire context.

---

# chatgpt response

**The current campaign brief processing pipeline is fundamentally flawed because it extracts user-provided campaign information into a small structured JSON representation, which destroys critical context, removes nuance, strips sales messaging, weakens objection handling, and prevents the AI from developing a complete understanding of the campaign. The entire campaign brief ingestion system should be rebuilt from scratch with a context-preservation-first approach: vendor scripts should be stored and passed nearly verbatim rather than summarized, campaign briefs should retain their full rich content instead of being compressed into a handful of fields, and structured extraction should be used only for metadata (project name, company name, pricing, location, etc.) while the original campaign content remains available to the model. The system should maintain both layers simultaneously: a structured layer for machine operations and a full-context layer for reasoning and conversation generation. Currently, the JSON extraction appears to be acting as a lossy compression layer, which is why the AI loses important details and fails to follow the intended sales flow. The redesign should treat campaign briefs, vendor scripts, FAQs, objection handling instructions, sales strategies, and uploaded documents as primary context sources, with retrieval augmenting them when needed, rather than replacing them with abbreviated summaries. The objective is not to create a cleaner JSON object; the objective is to preserve maximum campaign intelligence so the AI can behave like a trained telecaller who has read the entire campaign material, understands all project details, follows the provided script, answers objections naturally, and never loses context because of aggressive abstraction or summarization.**

---

# you asked

So like if the user on the phone call, they say, hey, I have to book the site visit at a specific time, and so on and so forth. So in the booking page, that should render, okay, the site person has booked the site visit. Now that should work every time because everything is 0, 0, 0. No matter if I actually test it, I call them, book the site visit, actually nothing is happening, nothing is updating. Also, I need a Google OAuth calendar. User can able to connect there, so you have to build the entire Google OAuth system so that I can able to connect my Google calendar and actually that will add for that particular specific time interval, that particular timeline, okay? You have to build that particular. Currently, the booking page, slash booking page, is just UI, nothing is working. It automatically, if the book site, if the site is completed, either AI you get to know or site or like manually they have option of this site has been booked because AI can, because if the site booked, the vendor going to show them site and they can also, if the AI get to know through the mobile or conversation, he can also complete it and do the stuff. But if not, AI get to know, he can also say book completed, no show, or cancelled, okay, perfect. Book the, make the entire system perfect and nothing is working like operations and integration and nothing is working in the new appointment and like, okay, so at the new appointment, either we can add manually, but the main thing is like on the call, whatever happened, whatever, that particular call or detail and everything, that site has been booked and added to the Google calendar. This system I have to build it.

---

# chatgpt response

**The entire appointment and site-visit booking workflow is currently non-functional and needs to be rebuilt as a complete end-to-end operational system rather than a UI-only feature. When a prospect books a site visit during a call, the AI must create a real appointment record, persist it in the database, immediately update the booking dashboard, and trigger all downstream workflows. The `/booking` page should become the single source of truth for appointments and support statuses such as Scheduled, Confirmed, Completed, No Show, Rescheduled, and Cancelled. Google Calendar OAuth integration must be implemented so vendors can connect their calendars, and once connected, any site visit booked by the AI or manually by the user automatically creates a calendar event in the correct time slot. During calls, the AI should be able to detect booking intent, collect the required details, create the appointment, and synchronize it across the booking system and Google Calendar. The system should also support manual appointment creation, manual status updates, and AI-driven status updates when call outcomes indicate that a visit has been completed, cancelled, or rescheduled. Currently, booking actions appear to stop at the interface layer with no database updates, workflow execution, calendar synchronization, or operational logic behind them. The redesigned architecture should ensure that every booking event triggers persistence, dashboard updates, calendar synchronization, status tracking, audit logs, notifications, and follow-up workflows so that a booked site visit becomes a real operational record rather than just a conversation outcome. The goal is that whenever a prospect agrees to a site visit, the appointment is automatically captured, visible on the booking page, synchronized with connected calendars, trackable through its full lifecycle, and reliably reflected across the entire platform without requiring manual intervention.**

---

# you asked

There is one more bug that I'm currently facing the bug is The knowledge base is broken it's like a school project the real retrieval augmented system those are well they are like production grid that we have to build it for example I can able to put lot of detail like any kind of PDA lot of tags or any kind of lot of scrapes or lot of You know objection handling entire book pdf could be whatever And AI will obviously try to do everything from its redis hot caching memory or the system prom and Where ever you get it the far if it is still did not get we obviously try to go with the retrieval argument rag system now But I really tested your rag system that we have builded I go to the knowledge base the page that you have created I go over there and I upload even pdf when I touch the answer actually it is not giving the answer and whatever knowledge base that you have created that hardcoded knowledge base That okay but actually the pdf that I have submitted and that actually not catching the data and not giving the answer from those Means like obviously rags system is not built like how production good systems are built and see yes you able to build rags system but make sure the rag system that you are going to well that like production rate millisecond in the like 50 millisecond 10 millisecond 15 millisecond in that I need that particular retrieved from their drug system I am broken I am stupid new idiot I don't know what is the right way to actually implement this pipeline like I need first complete low latency and best possible answer like real human telecollar because our goal is to replace the real human Dolly Gola means it should able to handle any kind of situation no matter of what any kind of situation and have crazy availability sales techniques sales method it is not just some normal ai that behave talk predefinance or some basic answer on the it have a those kind of abilities those kind of Those kind The Play music Those are those kind of crazy hidden capabilities like real cis person have He always It not push hard but use those Tricks method books Or some kind of sales techniques Okay either you can in either you can add in your memory System prom Or you can add in the retrieval argument system or could be wherever Or could be whatever do web is crazy techniques so that it make user to buy the property not forcing but actually make able to you know not it shouldnt look like a fake or something school project it actually a production grid real it is the core vision of the entire product The core product of the entire product from the The poor product of the entire product from the actually day one is like Replacing the entire human tele colour team And it shouldn't be a normal something that the current system that we have We have to use the entire computation we have to use the entire brain Or like you first have to use explore research web search red team design architecture create pipeline integration complete low latency crazy level low latency crazy level low latency with the crazy level result with the crazy result I really need a system a system that Actually entirely from end to end adaptive system that I already tell you in the previous that if you call today and if you able to find out our ai will give the summary and the basis of that summary it able to figure it out that this is the warmly means it could possibly interested lead or what lips so after next day After the next day on the very next day it tried to call back them and they very crazy time that you have to pick that time on basis of that or if they tell you then call on that time or else you decided you will call them and like You actually use those not just normal generic conversation is Structurally and very thoughtful Conversation deep thinking like how real says conversation whoever deadline to sell the two property in the 1 day that he's pushing hard his **** off Working hard to sell the property Aleria there I sell the property We are pushing hard to sell the property Like that particular note that for example that particular sales person who at the agenda calling that is pushing hard like a real tally caller who have a deadline to fill the property and he have 30 experience to actually sell the property those leads are completely cold leads make them warm and warm to the hot lid that kind of capabilities and this systems need to build this actual real system we you have to run multiple research loop learn every time by doing the multiple research thinking so hard with a multiple sub agent Middle East run two to three research loop with a crazy prompt very big prompt crazy context and and getting the crazy output from those running two to three phase of the research load and you will find out every time you will figure it out lot of new new things lot of new new things to way to do that because you know our pipeline our pipeline is we are using stt as servant 11 labs we are using ttt as a servant 11 lab 4 infra we are using live kit live kit and live kit is already plea 3 build I have seen that live kit have a most of things already we dont have to build those things the current thing that because the bargain is perfect interruption is perfect everything is perfect the core thing is like brain I thought what could be able to figure it out because it is like generic brain it because tts working perfect everything is so perfect okay I thought we have to obviously work on not everything is perfect I just say but thats not thing that everything is so perfect but the core thing is that the brain The how actually it is behave top adapt adaptive intelligence that is actually I thought missing in this particular layer what I able to figure out so you have to actually create this kind of pipeline integration do whatever May be the current way that we are using to create the system from that completely wrong and we have to revert those and do something so crazy maybe I am telling again that would be may be or maybe not I am just saying You because may be what have we have built what approaches that we have taken maybe try may be wrong could be because see I have searched lot of so that I have figured it out in the post grace we generally store the user id and whatever other mean main thing then we have a Main Mori and Memorial Contexts and all then we have redisk we have to use the Redis And then we have to also use for example retrieval document system we have to also use system prompts and we we also have to use lot of other things I dont know that you know See I say those are only one percent There are 99% things that are completely miss out completely blind spotted by me that you have to figure it out you have to solve this on the problem See please please note on this word you are core whole is to replacing the entire human telecollar team with this particular system now to do so to do so Do whatever what actually real time of team day they try to reschedule the call they automatically call back on the next day or same day not too much call 2 to 3 retry schedule the call book the they understand behave they make people able to convince to buy the property they push harder to sell the property because those have a deadline to sell the property and specific time line so they literally push so they literally push so hard so hard so hard to sell the property ok They literally push so hard to sell the property because they really want to sell the property They push hard he tried his **** off he tried his **** off now we have to build that system that AI will also behave like that and I thought Current LLM models and current everything is capable of doing the only thing that is wrong is from our side we have trained it wrong we have given things wrong I thought oversight we are completely wrong approach or completely architecture that we make that wrong could be See in the previous I will tell you I have tell this kind of stuff 5 to 6 times every time you run multiple ultracode workflow ultracode Workflow every time you try you yours of an at the end you **** **** and nothing is working perfectly so I really wanna go to go at its core to go at its dna obviously you have to search explore the entire code base and where we are actually mistaking what is the pipeline I have given the big pipeline but you already know what is pipeline where we are missing where we are actually completely branched for missing out all this stuff Then you have to search the entire web you know the text live gate stt groc as llm brain Grocu As LLM brand new or lady no so This system really work in the real time like obviously they are working but like I need that particular real human and also like I am I am not saying right or wrong you have to take the call I have seen that every input token is nearly about 10,000 token no matter of what every time user asks something its like around 10,000 to open and after the 10,000 token its generated roughness of 50 token 60 token or whatever Ah what do you think it it is the input token is too much II dont know because I know why I am because I am not a developer you have to take the call what would be the right approach maybe this is right May be this is the wrong because 10,000 open every time whatever user ask may be I thought right or wrong I do not know you take the call Completely go independently think like a researcher architecture plan or build 30 year plus experience who have build shaped production with this kind of stuff and actually able to achieve everything And you have future vision and you could able to do everything Okay and you have the entire developer team that is nothing but the multiples of multiple ultra code workflow and all these are nothing but the developers with the 38 plus experience and doing all this stuff and building the crazy probably single system with the complete low latency and all this stuff so what do you think about that what will be the right approach what something see I could able to figure it out Whenever I submit or create any campaign obviously if I add any PDF document notes everything I that is like complete knowledge base okay I should have either the current ui is also wrong I should able to add in that particular campaign detail And that in the real time whenever needed actually core it should able to fetch out OK that I thought that is not working and not randomly every time it should go to over there some because we need complete crazy level low latency if that we currently didn't have it We have to build crazy level low ladder so core goal would be the crazy level low ladens would be the best of the best of the quality May be there are lot of method or something that we can use it like before calling before calling before calling we can able to load everything that also I do not know that is right or wrong you take the call there are lot of thing read this or I already told you memory red is postgraded to your argument system context system prompt I dont know these are few things May be 10 more things take the call create the pipeline best of the best pipeline The the things is working see nothing is broken voice is perfect the core thing is either you hard coded lot of things or the adaptive the real human behaviour is missing Either the 4 missing thing is like wrong because TTS is speaking what LLM is giving OK so that's not the problem And we cannot put everything in the system from that also the thing means the rag system retrieval argument system which are working but every time we cannot call the retrieval document rag system we need it through radius and so on I do not know see I already tell you I am no beginner whatever I am telling I thats my rough cage broader idea or whatever I get it from Internet or whatever I learn over the period of time May be right may be wrong at the end see you know the core thing what we want to believe to build this kind of stuff to receive this kind of stuff you should know you should know what actually we need See now you have to go completely no **** independent independent if you need to change if you need to change the architecture if you need to change lot of thing you have the free access ground but at the end I need the region at the end I need the region if I told you about the past mistake the past mistake you have did it is like do not repeat it again please make sure language dont change or **** language language should be the adaptive for the stt and for the tts ok language should be adaptive and the Hindi it should be the Dev Nagari but it should be the casual Hindi for a problem with the current Hindi is speaking too much hindi for example instead of Yeh property Mahatma Poonai Mahatma Okay he is telling like that but in instead of that he should speak this here property was important as sir Like so there are few bulbs I thought I could able to figure it out brain and everything is completely wrongly structured wrongly See I do not know what would be the best optimal way to design this particular thing you are the architecture see Has explored the entire core base in our way like what actually we are actually facing I do not care how many ultracode workflow that you are going to run to explore I dont care if it takes Multiple phases each phases with the 15 subjects each phases and rendering the multiple phases to explore and come into the core diagnose then researching web searching crazy level researching and web searching with the crazy context and crazy context output so that we can take more and more and good decision then coming to the lot of researching planning planning phases with the multiple surveillances then architectural phases then crazy 2 to 3 phases with the red team red team red team is the biggest thing red team will be Crazy Actually implementing those solutions at this core and also one more thing dont try to do everything in the 1 file I dont think you can also create a 1 module a module so that that could be scalable in the future while you write the code base in future if you need to edit this code you also become very flexible and something so that you can do stuff so see at the end I am lefting on you everything at the end you have to take the call

---

# chatgpt response

**The core issue is not STT, TTS, LiveKit, barge-in, interruption handling, or the telephony stack; the primary failure is the intelligence layer, specifically how context, memory, retrieval, campaign knowledge, sales behavior, and conversation strategy are orchestrated. The current knowledge base behaves more like a basic document upload feature than a production-grade Retrieval-Augmented Generation system because uploaded PDFs and campaign documents are either not being indexed correctly, not being retrieved correctly, not being ranked correctly, or not being injected into the model context correctly when needed. The architecture should be redesigned around a hierarchical context system: persistent campaign data stored in the primary database, preloaded campaign intelligence cached before calls begin, full campaign briefs preserved without aggressive summarization, vendor scripts retained nearly verbatim, conversation memory maintained throughout the call lifecycle, and retrieval used only when information is missing from the active context. Retrieval should be treated as a fallback knowledge source rather than the primary source for every response, enabling lower latency and more natural conversations. The AI should behave like an elite human sales representative rather than a generic assistant, maintaining awareness of lead temperature, previous interactions, objections, follow-up commitments, booking intent, site visit status, and campaign goals. It should dynamically adjust its sales strategy based on the prospect's engagement level, ask intelligent follow-up questions, schedule callbacks, remember prior discussions, handle objections naturally, and progressively move cold leads toward warm and hot lead states. Vendor scripts should guide conversation structure, while campaign briefs, knowledge bases, and uploaded documents provide factual knowledge. The system prompt should focus on behavior, reasoning, conversation quality, language adaptation, compliance, and sales methodology rather than storing campaign content. Language handling should remain fully adaptive, switching naturally between English, Hindi, and Hinglish based on the prospect's responses while avoiding unnatural or overly formal phrasing. The retrieval layer should support large PDFs, FAQs, objection-handling guides, sales playbooks, brochures, project documentation, and campaign materials, with accurate semantic retrieval and low-latency access when deeper knowledge is required. The overall redesign should eliminate hardcoded conversational behavior, eliminate lossy campaign summarization, preserve maximum context, improve memory management, strengthen retrieval quality, improve sales intelligence, support appointment scheduling and follow-ups, maintain lead-state awareness across calls, and create a modular architecture where behavior, campaign knowledge, memory, retrieval, telephony, booking, and analytics are separate components that can evolve independently. The ultimate objective is an adaptive AI telecaller that operates like a highly trained human sales team member: fully aware of campaign context, capable of handling deep questions, skilled at objection handling, capable of scheduling and managing follow-ups, able to retrieve knowledge instantly when needed, and continuously guiding prospects toward conversion through natural, context-rich conversations rather than scripted or hardcoded responses.**

---

# you asked

In the past, you already did it. So for example, Hulk code a lot of letters that broke the system, so I have to revert the code to solve this problem. In the past, you have deleted a lot of mistakes whenever I tell to solve the problem. To change the language, you did a lot of unnecessary stupid things. Your response sometimes becomes too much long, too much short. The past mistake is that I'm telling, sometimes you are able to make the graph too much long, too much short. And by a lot of hidden drives, the complete system is capable of saying the response according to the needed. But this is broken at which code brilliant. See, see, I am telling the one thing you have to completely know, no matter what, it's like how real human telecaller actually, how real human telecaller speak, think, behave, how they ask the question, how they convince the people, how actually they greet, behave, act, think, process, work. Okay? Like, see, that actually need a hardcore, deep web search, extensive, deep web search, a deep web search with every deep web search agent giving you a very big context. I don't know how big context. Because the more bigger the context or output they give, the better the result you can able to take it. So also, give a very, very big prompt to context so they can take the and do an extensive web search. I don't care if you run five phases in just researching, web searching with each phases with a 15 sub-agent, but I need entire code. Also run two to three phases with the explore. So it's read the entire code, where it's all breaking. If the architecture is wrong, completely swap there. And where something so perfectly modular or could be whatever that what should be the perfect way to build it. So the entire pipeline should be working. And one more thing, the biggest thing that you should focus on, please create a complete different branch, different branch, create it. We will test it and merge it. Okay? So that in if any bug, we can able to revert it.

---

# chatgpt response

**A major lesson from previous iterations is that fixes were often applied by hardcoding behavior into prompts, language rules, response templates, objection handling, and conversation flows, which temporarily solved one issue but introduced deeper architectural problems elsewhere. Future work should not modify the live system directly; instead, all major AI-brain changes should be developed in a separate branch, tested extensively against real call scenarios, and merged only after validation so regressions can be easily rolled back. The redesign effort should begin with a full audit of the existing intelligence pipeline, including campaign ingestion, vendor script processing, memory management, Redis caching, retrieval systems, prompt orchestration, call state management, lead tracking, booking workflows, and response generation logic, to identify where hardcoded assumptions are overriding dynamic behavior. The primary design principle should be that the AI learns how to behave from its behavioral framework, campaign context, vendor scripts, historical interactions, and retrieved knowledge rather than from fixed response templates. Response length, language selection, tone, greeting style, objection handling, qualification depth, and sales strategy should be adaptive to the conversation rather than statically enforced. The system should model how experienced human telecallers operate: greeting naturally, confirming identity, building rapport, qualifying needs, handling objections contextually, adapting language dynamically, scheduling follow-ups intelligently, and gradually moving prospects toward conversion without sounding scripted. Campaign knowledge should remain dynamic, vendor scripts should override default conversation flows when provided, retrieval should supplement knowledge rather than replace it, and all architectural changes should be modular so that memory, retrieval, telephony, sales intelligence, campaign management, booking, and language systems can evolve independently. Before implementation, the entire codebase should be analyzed to locate hidden hardcoded behaviors, prompt conflicts, context-loss points, retrieval failures, language-generation issues, and response-quality bottlenecks, with all major improvements isolated in a dedicated development branch so the production system remains stable and every change can be tested, validated, and reverted if necessary.**

---

# you asked

In the UI you have broken the entire UI my vendor and they are complaining complaining is he is simply saying like you have lot of ui All the analytics dashboards crm leads everything is at broken Actually they need at one place and but they need everything do not try to compress everything at one place I am giving you freedom I do not know whatever for example if you really see the in intelligence you have analytics that are at different place dashboard is at different place CRM at is a different place also there are other stocks so that we can see the analytics They are broken Everything has different different place even nothing is updating in the real time I have I have live tested live tested call happen but nothing have updated in the real time every single data that we have on the website everything should updated in the real time whatever please please please this is a **** operation you have to do this entire pipeline is broken please resolve this also Also you have built the ashmat dash mode analytics so and so **** idiot **** but my person tell that hey you didnt build this what actually the Delhi report section where I can get enterment Delhi report my monthly report weekly report I can able to figure out click on any day and see the entire report any day click on any range and see the entire report of that and report should be like also we can able to I have already tell you in the past if you see in my previous message about text how will you tell you like we have we can able to philtre out according to the campaign wise according to the lead lead hot warm wise we can able to select according to the what we can say like multiple philtre that we needed and the about the ui **** **** you have to take the call about the you hire the front end developer please hire the front end developer everything is completely scattered completely scattered with the multiple pages multiple pages and I am also piece of completely **** **** and I do not want or I don't want to **** myself more and more So I really want to go to more deeper and deeper at its core dna Like I am why you have scared The possible best V or something see first we have to use the same UI or same something that we already have in the core 2 dashboard that template that we have usedDon't try to merge everything in all one pages. That will also break. Whatever you, whenever you try to hire a front-end dev and actually see the pages, you're actually able to figure it out, okay, this page, this detail should be here, here, here. This what do I need to build it. This one we need to replace is what, this is what I need to update it and so and so forth. The current UI is broken at its core and the biggest bug is like nothing is updating in the data. About the recording, I have also tell it, the recording was also not getting even after the call happened. Also, there are a few more bugs. I have added new lead. I called them. The call happened. But I didn't get their recordings. So that's the biggest bug. Also, like I am cannot able to see their update. He is the hot lead. I cannot able to see the update of the hot lead in the CRM or other. So entire pipeline is broken at its core. If you see the UI of the run campaign, uh, it's good, but it's a very, it's not friendly. Means like, no matter if we need to take the multiple steps, but each step should be clean and able to take the fast decision. It have a very minimum, minimum, very minimum tags. Tags is very small. Font is very small. It's could not able to visually not perfect. Try to do something more perfectly, hire a front-end dev or do whatever thing, but works perfect and do something so crazy. And in the WhatsApp page, we have a heading so that we can go to the multiple pages, that top page. That's what I need. That's a lot of UI. You have very bad UI in the run campaign page, what I can able to see. That's broken because you have tried to build the UI from your side. We have already pre-built templates, pre-built pages, so use those pages. Okay, please, please, please.

---

# chatgpt response

**The platform currently has two major classes of failures: operational pipeline failures and information architecture/UI failures. On the operational side, real-world events are not propagating through the system correctly—calls complete but recordings are missing, lead statuses are not updating, CRM records are not changing, analytics are not refreshing, dashboards are showing stale information, bookings are not synchronizing, and live call outcomes are not being reflected throughout the platform. Every call event should flow through a unified event pipeline where recordings, transcripts, summaries, lead status changes, campaign metrics, booking actions, follow-up tasks, CRM updates, and analytics updates are written once and then propagated everywhere in real time. On the UI side, the platform has become fragmented, with analytics, CRM, intelligence, reporting, campaigns, and operational views spread across disconnected screens, making it difficult for users to understand where information lives. The solution is not to force everything onto a single page, but to create a clear information architecture where each area has a distinct responsibility while remaining tightly connected through consistent navigation, shared filters, and unified data models. Reporting is also incomplete because users need daily, weekly, monthly, custom-range, campaign-level, agent-level, lead-status-level, and funnel-level reporting with drill-down capabilities, allowing them to click any date range, campaign, lead segment, or outcome category and immediately see detailed performance metrics. The Run Campaign experience needs a complete UX review because it currently prioritizes implementation convenience over operational usability; typography, spacing, hierarchy, workflow structure, and information density should be redesigned so users can make decisions quickly and confidently. Existing design systems, templates, and proven UI patterns should be reused wherever possible rather than introducing entirely new visual patterns that create inconsistency across the product. More importantly, the entire platform should be audited from an event-driven perspective: every action taken by the AI, user, CRM, booking engine, telephony layer, calendar integration, and analytics system should generate updates that automatically appear throughout the platform in real time. The objective is to transform the system from a collection of disconnected pages into a unified operational platform where calls, leads, bookings, recordings, reports, analytics, campaign performance, and CRM data remain synchronized, instantly visible, and consistently accessible regardless of where the user enters the workflow.**

---

# you asked

My particular vendor needs something different, or like, not a different, but his actual intention, what the need is perfectly genuine need. His need is something like, see, he told me that I need daily reports, like I should have something in dashboard so that I can see today reports, the entire thing, what actually happened today, how many calls and like how many dials connected, how many are involved, and so and so forth. Entire today's report means we have to create a system in the CRM dashboard. By default, it will show the entire, we have a range picker, date picker, or something called filter, so that when figure filter out the day, weekly report, monthly report, or we have a daily picker. We can pick the date and we can see the entire report of that specific date, or we can pick a range also, so that we can see the entire thing. For example, we pick a range of 2 July to 5 July week, so then it will show the entire detail what happened between 2 July to 5 July, how many calls have been dialed, how many, how many, how many, how many, like all the entire thing. Got it? On the main dashboard, and it should have a daily report, something called stuff.

---

# chatgpt response

**The reporting requirement is not a separate analytics page but a first-class dashboard capability. The main CRM/dashboard should include a global date filter and range selector that drives all metrics on the page. By default, the dashboard should show Today's Report, displaying all activity that occurred today, including total calls dialed, connected calls, answered calls, missed calls, average call duration, recordings generated, appointments booked, site visits scheduled, completed visits, hot leads, warm leads, cold leads, interested leads, not interested leads, callbacks scheduled, human handoffs, conversion rates, and campaign-wise performance. Users should then be able to switch between Today, Yesterday, Last 7 Days, Last 30 Days, This Month, Previous Month, Custom Date, and Custom Date Range. When a custom range such as 2 July to 5 July is selected, every dashboard metric, chart, table, lead count, funnel, and performance indicator should automatically recalculate using only data from that period. Additionally, users should be able to drill down by campaign, lead status, source, booking status, agent/AI, and other filters without leaving the dashboard. The goal is that a vendor can open the dashboard and immediately understand exactly what happened during any selected time period, rather than navigating through multiple pages or manually compiling reports. This should function as a unified reporting layer where all operational data is aggregated in real time and filtered dynamically based on the selected date or date range.**

---

# you asked

It didn't show any lead score or something because he's not a technical person. He just needs simple things, but what actually needed, like a hot lead, warm lead, cold lead, something like that, how actually they need this kind of stuff. Okay. And they need, if the warm lead, they get the AI summary or whatever, and AI will follow up the warm lead automatically on the retry basis, okay, that kind of system. Not the lot of retry or retending calls. A significant what industry standard or the what are the perfect way to call back the warm lead and according to the previous summary or whatever, where actually they fucked up or like where we fucked up, we actually have to make that AI should be continue the conversation with the previous where they left off and like start making more and more aggressive to become a buyer with the hot lead, okay, something like that. In the CRM, they could completely able to, not the CRM, wherever in the dashboard, they could able to filter out according to hot, warm, cold lead with their particular crazy batches look good. There one more big bug happened. Bug is like I wanted to, we have restored the record. After the call happened, instant recording should be appear and can able to listen. After the call happens, recording is taking 20 or 30 minutes, even the one hour or like I don't know variable amount. I didn't able to exactly find out, but it's taking a lot of time. And I cannot able to hear the recording. I really want, after the call, instant, instant recording should come on my dashboard. Instantly, instantly, transcript, instantly or whatever. In the WhatsApp follow-up, like, they have the entire WhatsApp system page that have multiple steps, where we have to create the banner, okay? So I need to add just one more option. They say me, like, I don't want to create a banner, I actually created with my designer, they hand over me. So like, we should have an option called add a banner. They will click on the add, they select the file from their laptop, computer or their phone or wherever, they can add that particular banner. That's the system that we needed. Same with the video, they can add a video or whatever, okay? And they will, whenever they send a WhatsApp follow-up, they can able to send. I need one more option. One more option in the WhatsApp called a brochure. Like, currently we have only image, the banner, banners, okay? They can click on the banner, this banner has been sent. Now, another option that I need that is independent from the template, while they send a WhatsApp message, what we need to send it with that particular template. Because template need verification. Now, what they actually need to send it with that, one is called brochure, a PDF, the brochure. Now, how? Create one more step, like we have a multiple step called 11th step, add one more step called brochure. They can add a file, they can preview older brochure, like entire system, like that kind of stuff. They can preview a current, they can click on older to preview older and the entire of that page. They can click, okay, I want this brochure, continue. The banner, perfect. And they have multiple other instead of banner, they have another image also they want to share. So, have a option also, so what kind of image that you also want to send with that. And the video option, which video that you want to send. These are all, they select from their laptop, computer. When they click, they actually get it from that laptop, computer, phone, and we will, they can, after that select all those templates, banners, air banner, image, video, brochure, all going to be sent to that particular, not that particular, to the all the hot leads or to the all the leads that they have selected autonomously. That kind of system that we have to build it and that should work in real time, end to end.

---

# chatgpt response

**The platform should be optimized for business users rather than technical users, which means dashboards should focus on intuitive lead categories such as Hot Leads, Warm Leads, Cold Leads, Site Visits Booked, Interested Leads, Follow-ups Due, Callbacks Scheduled, and Conversions instead of exposing abstract lead scores. Every lead should have an AI-generated summary, conversation history, last interaction details, next recommended action, and current status. Warm leads should automatically enter a follow-up workflow where the AI schedules callbacks using sensible industry-standard retry intervals, references previous conversations, remembers objections and interests, and continues the discussion from where it last ended instead of restarting from scratch. The dashboard and CRM should support filtering by Hot, Warm, Cold, Booked Site Visit, Callback Pending, Not Interested, Converted, and other business-friendly categories with clear visual indicators and counts. Another critical operational issue is recording latency: recordings, transcripts, summaries, call outcomes, lead status updates, and analytics should appear almost immediately after a call ends rather than being delayed by many minutes, ensuring users can review conversations and take action without waiting. For WhatsApp automation, the current media workflow is too restrictive because businesses often already have professionally designed assets. The system should therefore support direct uploads of banners, images, brochures (PDFs), videos, and other campaign assets from a user's device, along with media libraries where previously uploaded assets can be previewed, selected, reused, replaced, and organized. During WhatsApp campaign setup, users should be able to choose which template to send, attach one or more images, attach banners, attach videos, attach brochures, preview all selected assets, and then distribute them to the selected audience segment such as Hot Leads, Warm Leads, Booked Site Visits, or custom filtered groups. All uploads, media selection, campaign execution, lead targeting, delivery tracking, and engagement updates should function as a complete operational workflow rather than just a configuration interface, ensuring that media assets, follow-up automation, lead management, recordings, summaries, and CRM updates work together in real time as a single integrated sales platform.**

---

# you asked

Currently, one more issue is like, whenever I click on the Servam TTS, that is actually not working. Like, whenever I select a plan called Lean or less than premium, that actually have TTS as a Servam. Whenever I call, nothing is working in complete silence. It's like Servam. Either Servam kind of stuff is not built it, so you have to build that particular stuff. Or if you have already built it, please make sure that when I click on the Servam, it should call the Servam, okay? So call with the TTS should be the Servam. Perfect.

---

# chatgpt response

**There appears to be a critical TTS provider integration failure in the Servam voice pipeline. When a user selects a plan that uses Servam TTS instead of the premium voice provider, calls are connecting but no speech is being generated, resulting in silence during the conversation. This indicates that either the Servam integration has not been fully implemented, the provider selection logic is not routing requests to Servam correctly, authentication/configuration is failing, audio generation is failing silently, audio streaming back into the call is broken, or the system is falling back incorrectly without reporting errors. The expected behavior is straightforward: when a campaign, workspace, or subscription plan is configured for Servam TTS, every generated response should be synthesized through the Servam provider and streamed into the live call exactly as the premium provider does. The system should also include health checks, provider validation, error logging, fallback detection, and diagnostics so that if Servam fails, operators can immediately see whether the failure occurred during provider selection, API communication, synthesis generation, audio conversion, or telephony playback. From a user perspective, selecting Servam should simply result in a working voice conversation with no difference in operational behavior. This issue should therefore be treated as a core telephony-path bug because a call that connects but produces silence effectively renders the AI agent unusable for customers on Servam-based plans.**

---

# you asked

So one more thing is like, at after the entire day happens, the entire summary, everything goes to that one specific registered mobile number, the entire daily summary and everything, the big summary, and all the, if there is a multiple hot leads, hot lead names, and there all the hot leads name and their age sort summary also sent to that particular mobile phone number. There is one more thing. One more thing is like, see, AI manager. AI manager is fetching wrong details, means like it should fetch the real-time detail, what we have, all the real-time updates, okay? The AI manager should fetch and find all the detailed real-time detail, end-to-end detail of the entire platform so that the particular AI manager of the vendor could ask any question, any info, any detail. He can also give the instruction on the mobile, send me this report to my WhatsApp, and so on and so forth. For that on a specific mobile number. I need the complete flexibility and so much flexibility and so much comfortability, and so much like if something, so that I can able to vary, like I can able to have the entire data, I can enable multiple filters, or like I can able to do whatever, for example, according to the hot lead, warm lead, or whatever lead, and so on and so forth. also the recording, whenever a user launches a campaign or wherever, they have options also like how do you want to store the recording of all of the leads. Like they ask the timeline for the one month, for the weeks, or whatever, okay. Same with the transcript, they ask them, like, how do you want to store the transcript? Because, see, we didn't have the infinite storage or we didn't have the infinite something, okay. So after the specific time period, all the call recording and all the transcript will be vanished, okay. Whatever user, that particular client or vendor that have selected, first we ask them, hey, how do you want to store the transcript, how many timeline. They can select both differently, like, I want to, for example, I want to record the recording stay for one month, two months, or any custom timeline, any range timeline or day pickup, whatever. They can also do the same for the transcript also, okay, the AI transcript and all this stuff, okay. So we cannot store all the things for the lifetime. So that also we needed.

---

# chatgpt response

**The platform should include an executive reporting and retention layer designed for business owners rather than operators. At the end of each day, a comprehensive daily summary should automatically be generated and delivered to the vendor’s registered mobile number through WhatsApp and/or other configured channels. This report should include overall campaign performance, total calls placed, connected calls, answered calls, missed calls, appointments booked, site visits scheduled, conversions, callback requests, campaign performance breakdowns, and a dedicated Hot Leads section containing lead names, contact details (subject to permissions), AI-generated summaries, last conversation outcomes, next recommended actions, and follow-up status. The AI Manager should operate as a real-time business intelligence assistant connected directly to live platform data rather than stale or cached snapshots, enabling it to answer questions about campaigns, leads, bookings, recordings, conversions, reports, performance trends, and operational metrics using the latest available information. It should also support command-based actions such as generating reports, filtering by campaign, lead status, date range, or performance category, and sending reports to approved destinations like the registered mobile number. Additionally, the platform should introduce configurable retention policies for recordings, transcripts, summaries, and related artifacts. During campaign setup or account configuration, users should be able to define how long recordings and transcripts are retained, including preset options such as 7 days, 30 days, 90 days, 6 months, 1 year, or custom durations. Recording retention and transcript retention should be managed independently, with clear visibility into storage policies and automatic cleanup workflows once retention periods expire. This creates a scalable storage strategy while giving customers full control over operational history, reporting, compliance, and cost management. The overall objective is to transform the system from a simple calling platform into a real-time operational command center where business owners can receive automated executive summaries, access live intelligence through the AI Manager, control data retention policies, monitor lead pipelines, and manage the entire sales operation without manually collecting information from multiple sections of the platform.**

---

# you asked

So there is one more bug. I don't know why the entire timeline is showing is not correct. Like I did a call just now. It showed it started one day ago. And timeline, I don't know, UTC may be right or wrong would be whatever. Currently, like I call at the 11th PM, it's showing old, recent, another time. Means the entire timeline should be broken. I need exact real time, exact real timing in every manner. Okay? Okay, perfect. See, I need to also need even a place where, obviously, whenever we click on the CRM, user profile, we can see all the recording. But I need a specific platform, platform, so that I can see all the recordings, all the recordings. But instead of doing that, what if, what if in the call log that we have it, where whenever we click on the call log, first thing is timeline is showing that is completely wrong. Please resolve that. Second thing is like whenever I click on the call logs, it shows all the transcript and everything. So now we should have an option, two columns. One called transcript, one called recording. When we click on the recording, it actually shows all the recording. Okay? Now we need a filter, okay, according to the timeline. So it will be filtered out according to that particular timeline. Okay, perfect. Of the recording basis and the transcript basis, because both happen at the same time. Like in the call log, I can also sort according to the name, campaign, status. Okay, perfect. I don't know what the fuck that you have did in the entire codebase. All are the outdated dates, all are the old dates, everything is like old. Why is that fucking idiot, fucking more fucking idioteness happening?

---

# chatgpt response

**There appears to be a fundamental timestamp and event-synchronization issue across the platform. Calls that occur in real time are being displayed with incorrect timestamps such as "1 day ago" or other inaccurate times, which suggests a problem with timezone handling, UTC-to-local conversion, event storage, frontend rendering, server time synchronization, or a combination of these. Every call, recording, transcript, lead update, booking, and analytics event should be stored with a canonical timestamp and then consistently rendered in the user's configured timezone so that all timelines, dashboards, CRM records, call logs, reports, and AI Manager responses display the exact same time. The call logs section should evolve into a dedicated operational history center where users can browse all calls, transcripts, and recordings from a single interface. Instead of only showing transcripts, the interface should provide separate Transcript and Recording views, allowing users to switch instantly between reading the conversation and listening to the call. The call log should support filtering and sorting by date range, campaign, lead name, phone number, call status, hot/warm/cold classification, booking status, duration, recording availability, and transcript availability. Recordings and transcripts should appear almost immediately after call completion and remain synchronized so that selecting a call gives access to the complete conversation history, recording, transcript, summary, lead details, and campaign information in one place. More broadly, the platform should treat time as a first-class system-wide concern: dashboards, CRM, bookings, recordings, reports, notifications, analytics, AI Manager responses, follow-up schedules, and retention policies must all reference the same authoritative timestamps to eliminate discrepancies and ensure that users always see accurate, real-time operational data.**

---

# you asked

So the current entire system is broken. Broken in the sense, still whenever I click on the voice icon play button, RECOFRING did't play either take too much or did't play lot of recordign did't appear even after call done that also issue also in voice like tts voice previs on run page tts voice previw i can't able to previos voie like it paly for 1 to 2 second and stop atleadt it paly for 5 to 7 second even in elevan albs it's play 5 to 8 secondno voice is playing, completely silent. First thing. Second thing, please, please, please, please, please do real web search and find the real data, not fake data. Current, the premium lean plan that you have created and put all of those price, those are completely fake and completely wrong. Go do deep web search. Find out all the real thing about Servum, 11Labs, and Provider, and all this stuff. We have Wobbies telephony provider, and all this stuff, so that we can able to give the exact price, okay, how much price is going to be cost, okay, on basis of all the data or whatever. You have to actually in-depth web search about that. do intensive web, you have to exactly find out exact price at the end, for what were the total and everything. Getting the context, there should be the perfect price, not something that fake or something like that. And what exactly new feature and function something that you can add it. By default pacing and cap, hourly cap and whatever by default, they can update, but by default should be the whatever in their particular plan they have, okay? And you can also add more feature and function or something more, more flexibility and more also you can add it. Whatever you want, you can add it from your side. I don't get a shit. I cannot able to hear voice from the Servom or Eleven Labs, so resolve that particular, I cannot able to hear the preview. And make sure, make sure, make sure, in this particular voice selection, the provider selection, it actually works in the real time. If I select that voice, AI agent should call with that voice. If I select TTS provider as Servom, it should be the Servom. It never ever calls the Eleven Labs. Means my cost would be the goes to the Servom. Getting the cost, getting the point. At the end, whatever I select, everything should be that one, and I pay for that one. Getting the context? Go ultra crazy.

---

# chatgpt response

**The voice infrastructure currently has multiple critical failures that affect both usability and billing accuracy. Voice previews are not functioning correctly because preview playback either remains completely silent, stops after one or two seconds, or fails to load entirely. Voice previews should consistently play a meaningful sample (for example, 5–10 seconds) so users can properly evaluate voices before selecting them. Additionally, provider routing appears unreliable: when a user selects a specific TTS provider such as Servam, the entire voice pipeline—including preview generation, live calls, and billing attribution—must use that provider exclusively, without silently falling back to another provider. The selected provider should become the authoritative voice source for previews, test calls, live campaigns, usage tracking, and cost calculations. Recording playback is also unreliable because many recordings either never appear, appear after excessive delays, or cannot be played even when visible. Recordings, transcripts, summaries, and call metadata should be generated, indexed, and made available almost immediately after call completion. On the pricing side, subscription plans and usage estimates should be derived from real provider costs rather than manually entered assumptions. Plan construction, usage forecasting, included minutes, overage calculations, provider-specific costs, and margin calculations should be based on actual provider pricing and infrastructure costs, with a transparent pricing model that remains accurate as providers update their rates. Operational controls such as pacing limits, concurrency limits, hourly caps, daily caps, usage quotas, and campaign restrictions should inherit sensible defaults from the selected plan while remaining configurable by the customer. More broadly, the platform should treat voice provider selection as a core system dependency: the chosen provider must consistently control previews, live synthesis, usage accounting, analytics, reporting, and billing so that customers receive exactly the service they selected and are charged according to the provider actually being used.**

---

# you asked

Web search There are in the voice, I could able to figure out a few bugs. See, what if we use some fillers? Fillers, what if we use some fillers, fillers in the sense, go web search about what kind of 11 labs, 11 labs support some punctuation, 11 labs support some fillers, and they behave and act on that. What if, like, we can able to create some human intelligence and the AI agent actually behave on those, like, we're not using too much in excess amount, but according to need. See, the quality that I get able to figure it out, the core thing is that we don't have to hardcode anything in the voice. We don't have to hardcode anything to our system. We have to be adaptive intelligence. Adaptive intelligence. AI adaptive intelligence. So that see, adaptive intelligence in the sense, it should auto-adapt instead of putting hard coding toward system, everything, like fillers, like punctuation. The core thing would be the LLM brain. What if, and that's the perfect way, because I have, in the past, I have tried to put the hard-coded thing and they broke the entire system. Please, please, please never, ever attempt or even think of this, doing this thing. You can do in the system prompt, you should tell, first you have to do two to three or five website. Because we have two model providers, one is Sarvam, one is ElevenLab. So what actually fillers, what actually punctuations, what kind of other something-something that they follow, or just serve their documentation, once you have final, okay, this, this, this, this support. Now, the grok LLM, that response going to be generated, that should be the normal response, but now they will start with fillers, for example, could be whatever, not hard code any fillers, and not even tell grok to every time start with that. It should be the adaptive, whenever it needed fillers, like filler is genuinely needed, use at that point of time. And punctuations, punctuations, because Sarvam and ElevenLab, they behave and act on those punctuations. So I really like those, so suppose please don't hard code, and also don't tell grok LLM to hard codely use punctuation, don't tell hard codely use fillers. That should be the adaptive, adaptive according to need, if there is a needed of punctuation, if there is a needed of filler, then use it and make it look like real. That could be a possible way to reading. So in that you can also run Explorer agent, web search agent, this we have the system, then Explorer web search agent, multiple web search agent, then Design plan, then a crazy red team will run, the red team that actually find out all the things, what could make this system perfect, if there any problem should happen. Because in past I have whenever I try to code fillers, first I put it hard-coded fillers, broke entire system. I have to revert. Then it put the fillers and telling the grok, so that the grok giving the response every time it start with the same filler or always start with the filler or something like that, and unnecessary using the fillers. That also make the system rough. I have to also revert that. But now because we have learned a lot of After doing a lot of mistakes, we have learned a lot of things, okay? So we have learned a lot of things over a period of time. So now, because we have learned, so just do a lot of things, explore, search, web, thing, design, red team, and come to the complete diagnosis. This is the way to achieve the real human, because, see, actually, 11 lessons have their own documentation. Whenever you run a web search, you will be able to figure it out that 11 lessons have a documentation to touch the real human call, documentation called fillers and the punctuations. So they tell us, like, if we use those punctuations, if we use those fillers, we actually behave and act, okay? So that touches actual real human, way more human team. So they have some way to, they take pause, they behave, act, think. So they have everything pre-built. So we don't have to build hard-coded things. Please, please, please, don't put any hard-coded thing. We have to, should be dynamic, adaptive. And that should come from the agroc LLM brain response, whatever response that we are giving, the TTS, the TTS have those capabilities. Surviving and 11 lessons have those capabilities. So behave, act, behave and act on those fillers, act on those punctuations that actually really touches the real human touch. So that's what we have to work on. That's what we have to build it. So that also one more thing that could able to touch the real humans. But the core thing that should we have to completely work out, it should be the real human brain. Brain means how to talk, what to talk, how much to talk, what to ask, and so on and so forth. Like it is asking unnecessary questions. It is speaking unnecessary, a very damn. Hardcore Hindi, that didn't even make sense. And asking another question, it should be so adaptive intelligence, so adaptive intelligence. And one more bug that I figured out, my researcher told me, my researcher told me that the entire memory, the entire context of the chat history, entire context and entire memory of that particular person, that should be in the retrieval augmented system, the RAG system. I don't know, is it the right way or it is the wrong way? I don't know, fuck that. I don't know what it should right way and wrong way. You have to take the call. And then I need the low latency, low latency elevanla s and sarvam ignore typo in my message give me response how we are going me giving me in the previous response

---

# chatgpt response

**The voice system should move away from hardcoded speech patterns and toward adaptive speech generation driven by the LLM and the capabilities already provided by the selected TTS engine. Rather than forcing specific fillers, pauses, phrases, punctuation rules, or conversational structures into the prompt or application code, the architecture should allow the model to decide when hesitation, pauses, acknowledgment phrases, emphasis, or conversational fillers are appropriate based on context, intent, lead state, and conversation flow. The TTS layer already provides speech rendering capabilities, including natural pauses, prosody, emphasis, pacing, and other speech behaviors, so the goal should be to generate high-quality conversational text that contains natural conversational structure without hardcoded filler insertion logic. Previous attempts to force fillers globally created repetitive and unnatural conversations, which suggests the correct solution is adaptive generation rather than rule-based insertion. More broadly, the intelligence layer should focus on human sales behavior rather than speech tricks alone. The largest opportunity is improving the conversational brain: understanding lead intent, remembering prior interactions, asking relevant questions, avoiding unnecessary questions, adapting response length, using natural Hinglish instead of overly formal Hindi, handling objections contextually, and progressively moving prospects through the sales funnel. Conversation memory should be treated as a dedicated subsystem rather than simply dumping everything into retrieval. Short-term call context, lead history, campaign knowledge, vendor scripts, summaries, follow-up commitments, and retrieval documents should each have distinct roles. Frequently used information should remain immediately available in active context, while historical conversations and large document collections can be retrieved when needed. This avoids excessive token usage, reduces latency, and improves consistency. The overall objective is an adaptive intelligence architecture where the AI behaves like an experienced human telecaller: it remembers previous conversations, continues discussions from where they ended, selects appropriate language automatically, adapts pacing and response length naturally, leverages campaign knowledge intelligently, uses retrieval only when necessary, maintains low latency, and generates speech that sounds human because of strong reasoning and context awareness rather than because of hardcoded conversational tricks.**

---

# you asked

My one of the senior tell me he is a PhD researcher. He tell me like, hey, where you are actually storing the contacts? Are you mad? I said that I don't know. Like, he tell me like, you should store the previous uh previous conversation, contacts, or everything in the RAG system. Like, are we actually doing that? Either I have told the AI to actually do that, either we are doing that, but either I couldn't able to figure it out that it is actually working or not, or actually, if we are actually using RAG system, therefore we have the complete low latency. Latency shouldn't impact at all, and we have to use the uh RAG system if the multiple conversation happens, if the WhatsApp conversation, multiple conversation happens, but we cannot store everything in the memory. We should use the retrieval augmentation RAG system, like production grade RAG system. So you have to also do web search, explore, deep think, deep think, deep think harder and make this entire pipeline integration so perfect. In the past, I have run the multiple workflows. You can see the workflow so that you actually get to know what has been created and what actually pending.

---

# chatgpt response

**Your senior is pointing at a real architectural concern, but the answer is usually not "store everything in RAG." A production-grade AI telecaller should use a layered memory architecture. Active conversation state (current call, current WhatsApp thread, current follow-up) should remain in fast runtime memory; structured lead information (name, phone, campaign, status, bookings, callbacks, lead temperature, last contact date, conversion stage) should live in the primary database; frequently accessed lead context and campaign intelligence should be cached for low latency; and historical conversations, transcripts, WhatsApp messages, call summaries, documents, brochures, PDFs, FAQs, and campaign knowledge should be indexed in a retrieval system. The mistake many systems make is either storing everything directly in prompts, which becomes expensive and slow, or storing everything only in RAG, which increases retrieval dependency and can make conversations inconsistent. The ideal architecture is hierarchical: the AI loads a compact lead profile and latest conversation summary immediately, then retrieves deeper historical context only when needed. For example, if a prospect says "I spoke with you last month about a 3 BHK unit," the AI should instantly know the lead profile and recent summary, while the retrieval system fetches the older conversation details if necessary. Similarly, campaign PDFs, objection-handling guides, brochures, WhatsApp history, call transcripts, and sales playbooks should be retrievable knowledge rather than permanently injected into every prompt. This keeps latency low while preserving deep memory. The broader goal is that the AI should maintain continuity across calls, WhatsApp conversations, bookings, follow-ups, and CRM interactions without repeatedly asking the same questions. Every interaction should enrich the lead profile, update the lead timeline, generate a summary, update lead temperature, and become available for future retrieval. The result is a system that remembers context across weeks or months, scales to large conversation histories, supports real-time responses, and behaves like an experienced sales representative who remembers every important interaction without requiring enormous prompts or excessive retrieval on every turn.**

---

# you asked

One more thing, at this point of time, we have this system prompt, system prompt around 10,000 tokens. Every request was that it hit the 10,000 input tokens. That also increased the latency, and that also didn't make sense. I don't know, maybe this is right, maybe this is wrong. Maybe this is the right way, maybe this is the wrong way. I thought we should have a Redis or the retrieval argument system prompt, what is balanced and so managed like a production-grade voice engine, like how billion-dollar companies, they manage and build this kind of production system. For that, you actually need crazy web search, crazy exploration with the multiple web search services, so you could able to figure it out all the things and build the entire thing so perfectly. Okay, see, don't repeat, I thought we maybe have a lot of already built. Already built. If we have already built, I have told in the past that use the RedPigi vector or whatever, but I don't know if it is actually working or not. That's the problem. Okay, so I literally, either that may be working, may not be, but either what I could able to figure it out is like, we have system prompt of 10,000 tokens. I thought we have built a PG vector, but that's never ever wire up and never have work in the real-time. So that first it should work in the real-time. And second, the biggest thing, please, please put your entire attention on this word. Whenever we use the RAG system, retrieval argument system, it should, it should have complete, nearly low latency, means like latency literally didn't even impact, less than 50 milliseconds latency or literally zero impact on the low latency. That's kind of RAG architecture that we have to create it. Go web search, deep thinking, deep thinking, think harder, use your entire computation.

---

# chatgpt response

**The concern is valid: a voice agent that sends a 10,000-token system prompt on every turn is usually not operating with an efficient production architecture. The goal should not be to keep adding more information into the prompt but to move toward a layered context architecture where each type of information lives in the correct place. Core behavior, safety rules, language adaptation, conversation quality standards, and telecaller methodology belong in the system prompt. Campaign details belong in campaign context storage. Lead state belongs in structured records. Recent conversation state belongs in active memory. Long-term history, transcripts, WhatsApp conversations, PDFs, brochures, FAQs, objection-handling guides, and campaign documents belong in retrieval systems. Frequently accessed information can be cached before the call begins so the AI already has the most important context available without performing retrieval on every turn. The objective is not to eliminate retrieval or prompts but to use each layer for the purpose it serves best. If a vector database such as PGVector already exists, the critical question is not whether it exists but whether it is actually integrated into the runtime decision flow, retrieving relevant information, ranking it correctly, and injecting useful context into the model only when needed. A production-grade voice system typically minimizes repeated context, avoids sending large static prompts every turn, preloads essential information before calls start, maintains compact conversation memory, and performs retrieval selectively for deeper knowledge. This reduces token usage, lowers latency, improves consistency, and makes the system easier to scale. More importantly, the retrieval layer should be treated as a support system rather than the primary source of every response: campaign context, lead state, previous summaries, vendor scripts, and active conversation memory should already be available, while retrieval is reserved for deeper questions, historical conversations, PDFs, FAQs, and knowledge-base lookups. The overall goal is a low-latency architecture where the AI always has immediate access to the most important context, uses retrieval only when necessary, preserves full campaign intelligence, maintains continuity across calls and WhatsApp interactions, and avoids repeatedly sending large amounts of static information that increase latency without improving conversation quality.**

---

# you asked

And please, please, please focus on this one thing. Whenever I create a campaign, they ask for vendor scripts, but that actually, this is not working. Whenever I put the vendor script, actually that AI is not speaking and behaving like that. It is speaking the same hard-coded thing that we have built in our system. For example, in the vendor script, I said that start with the, hello sir, good morning, then speak their name. Hello, I am speaking to Mr. something, whatever name, and then start the greeting. But, but, but, but, I put the vendor script and I launched the call, it is still speaking the hard-coded way of speaking that we have hard-coded in our system. Means that actual system is not working, that particular vendor script. Like we should have dynamic, like whatever script or something or instructions for the AI that have put in the real-time, whenever I launch a call, that should exactly adapt those kind of behavior and everything. Are you getting the context of what I am actually telling?

---

# chatgpt response

**Yes, the issue is clear: the vendor script is behaving like a stored field rather than an active runtime instruction. The expected behavior is that when a vendor provides a script, that script becomes the primary conversation blueprint for the campaign. Instead, the agent appears to be following a hardcoded default conversation flow regardless of what is entered in the vendor script field. As a result, even when the script specifies a sequence such as greeting based on time of day, confirming the prospect's name, introducing the company, waiting for confirmation, and then moving into the project discussion, the AI continues using the platform's predefined opening and ignores the campaign-specific instructions. Architecturally, the priority order should be: first, platform-level safety and compliance rules; second, the vendor script that defines conversation flow and behavior; third, campaign context and project knowledge; fourth, retrieved knowledge and historical context. The vendor script should not be compressed into a few extracted fields or treated as metadata. It should be passed as a high-priority behavioral instruction so the model understands how to conduct the conversation. If no vendor script exists, then the default telecaller framework can be used. The real bug is not conversation quality itself but instruction precedence: the hardcoded framework is currently overriding campaign-level instructions. The correct design is for the default framework to act only as a fallback, while vendor scripts dynamically control greeting order, introduction style, qualification flow, objection handling approach, discovery questions, booking flow, and conversation structure whenever they are provided. That way every campaign can have its own calling style without requiring changes to the core system, and the AI will behave according to the campaign-specific script instead of repeating the same predefined opening on every call.**

---

# you asked

And don't be a generic telecaller like he just asked. Just be honest with you. Please be honest. We should be honest with you. So actually sell the property to a person, which should exactly behave like a 30 years plus experienced person, okay, in the real estate salesperson or could be X, not the series, real estate. If I put whatever industry, it should behave like that. It uses all manipulative techniques. It uses all the hooks, tips, tricks, method, all the way of speaking. And it have a crazy objection handling skills. And he have, like I already told you three times, I'm telling again, for example, if a particular person, salesperson gets a deadline, you have to sell at least one property in a day, he will going to try his ass off, fucking ass off. He will try the entire computation, entire my entire whatever he have, and he's pushed his limit harder and harder to lock the deal or make that person to book the size, whatever. Getting the point? See, be honest with that. How actual real human telecaller. For that, what actually we need? Either a retrievable argument system in which we put the entire behavior or the system prompt or the memory, I don't know. Also, fuck that. Also, one more thing, where the context will be stored in the obviously retrievable argument system, the reg system, the entire context history, what subject, whatever that we already have discussed. That should be supplied also. Remember that, so fuck that. Everything, fuck, fuck, fuck. So see, the core goal you got to know, our core goal is to make AI so adaptive, it will auto-adapt according to the industry and it will exactly, exactly be a real human telecall. Be a thing, act, like everything. And don't, don't, don't, don't, don't, don't, don't hardcore anything, please. When you hardcore anything to the system, it breaks the system, okay? That's the bug that we have to resolve. I thought we have a lot of hardcoding. I didn't, fuck that, I don't care. If you want to hardcore, if you think that's the right thing, stay. If you think, okay, yes, you are right, we don't need to hardcore, we have to do something else, creating the voice intelligence adaptive layer or could be whatever. Take the call. You are the founder, you have to take the call. For that, you have to do crazy web search, run multiple ultra-code workflows. Each workflow have multiple phases. Each phases have at least, at least or minimum, minimum, minimum, 15, 15 sub-agents in each phase. And there is multiple phases in each workflow. And at a time, we are going to run multiple workflows, okay? Because this, the core heart, this is the entire core heart of the product, and entire architecture is completely broken, what I could able to figure it out. Every time I say the entire architecture is broken, you go web search and see the codebase map, all the things as well. Hey, already it's built it and everything is perfect. Yeah, fuck that, fuck, fuck, fuck. Everything perfect. And at the end, my product fucked up every time whenever I go to the production, fucked up my entire product. And that I don't want. Every time you say end-to-end product is perfect, you run explore, agenda, and map all the things and say, hey, we have all the things, end-to-end product done. And when I actually real product end-to-end product fucked up.
Please give me the response as you are giving me in the previous

---

# chatgpt response

**The core objective is not to build a generic AI caller that follows a fixed script, but to build an adaptive sales intelligence system that behaves like a highly experienced industry-specific salesperson. The current problem is not only that parts of the system are hardcoded, but that the architecture appears to treat conversations as generic call flows rather than dynamic sales engagements. The AI should adapt to the campaign, industry, lead state, prior conversations, objections, goals, and customer behavior. If the campaign is real estate, it should behave like an experienced real-estate salesperson; if it is insurance, it should behave like an experienced insurance advisor; if it is education, it should behave like an experienced admissions counselor. The expertise should emerge from campaign context, vendor scripts, industry knowledge, historical interactions, and retrieval systems rather than from hardcoded phrases or rigid conversation trees. Previous interactions, WhatsApp history, call summaries, objections raised, site visits booked, follow-up commitments, and lead status should all contribute to a persistent customer memory so that future conversations continue naturally from where they ended. The AI should actively pursue campaign objectives such as booking appointments, scheduling site visits, qualifying prospects, handling objections, and moving leads through the funnel, but it should do so through intelligent, context-aware conversation rather than repetitive or scripted persuasion. Architecturally, the system should separate behavioral intelligence, campaign knowledge, customer memory, retrieval, telephony, CRM updates, analytics, and workflow automation into independent layers, allowing each component to evolve without creating unintended side effects elsewhere. Hardcoded conversational behavior should be minimized because it tends to break adaptability, while dynamic reasoning should be strengthened through better context management, vendor-script prioritization, campaign-context preservation, lead-memory continuity, and retrieval integration. The retrieval layer should support long-term memory and deep knowledge access, while active context should remain lightweight and optimized for low latency. Most importantly, future changes should be validated against real-world call scenarios rather than only code-level assumptions, because the ultimate measure of success is whether the AI behaves like a skilled human salesperson who remembers context, adapts naturally, handles objections effectively, follows campaign-specific instructions, and consistently advances conversations toward meaningful business outcomes.**

---

# you asked

That is the crazy thing I am remembering you again. Eleven Labs and Servam. These are the TTS providers. And what I am able to figure it out, they have entirely built a real human voice quality system so that it feels like real human. They have punctuations, they have fillers, everything pre-built and in-built. So at the end, what do we have to do? The Grok LLM response that we get, we should get Servam-friendly, Eleven Labs-friendly response so that whenever TTS is going to speak, it will speak like whatever friendly to the Servam and the Eleven Labs. So when they speak, it feels like a real human. We don't have to build an entire thing for making the real human touch in the voice. The brain is broken, that I agree. The human touch, that can be achievable completely with the Servam-friendly, Eleven Labs-friendly response generating from the Grok LLM, the LLM brain, when TTS speaks. For that, don't do and build direct. Obviously, run multiple web search engines. I don't care fuck about that. Run the multiple web search engine that I get the entire real documentation from the Servam and Eleven Labs, what actually they have in our system, what kind of model that we are using, what they support and everything. And at the end, we are whatever the Grok response that we are going to get, we get Servam-friendly so that we also take the real human. That's what also missing. But the core thing is also completely broken, that is the Grok LLM brain. Okay? So you have to be that should be so adaptive and so perfect.

---

# chatgpt response

**A useful distinction is that there are really two separate problems: speech rendering quality and conversational intelligence quality. The speech-rendering side is largely handled by the TTS providers, which already support natural pacing, pauses, emphasis, prosody, conversational flow, and other speech behaviors. The goal therefore should not be to recreate those capabilities through hardcoded application logic. Instead, the text generated by the LLM should be optimized for spoken conversation so the selected TTS engine can render it naturally. This means the LLM should generate concise, conversational, human-friendly responses rather than robotic, overly formal, or excessively dense text. The system should avoid globally forcing fillers, pauses, or speech patterns because those approaches often create repetitive behavior and degrade conversation quality. Instead, conversational structure should emerge naturally from context, intent, lead state, and dialogue flow. The larger issue remains the intelligence layer. If the conversational brain produces unnatural questions, overly formal language, generic sales behavior, repetitive objection handling, or ignores campaign instructions, then even the best TTS engine cannot make the conversation feel human. The architecture should therefore prioritize improving the reasoning layer: vendor scripts should influence conversation flow, campaign context should remain rich and intact, lead history should persist across interactions, retrieval should supply relevant historical and campaign knowledge when needed, and the model should adapt dynamically to industry, prospect behavior, conversation stage, and lead temperature. The TTS providers should then be treated as high-quality speech renderers that convert those naturally generated responses into realistic speech. In practice, this means focusing on making the generated text conversationally intelligent, context-aware, adaptive, and industry-specific while ensuring the provider-selection pipeline, preview pipeline, and live-call synthesis pipeline reliably use the chosen TTS provider. When those pieces are aligned, the resulting experience feels significantly more human without requiring extensive hardcoded speech behavior throughout the application.**

---

# you asked

In the retrieval-augmented system, we have a lot of objection handling and that we already have. Will it take the call, what you actually need for retrieval-augmented system? Why it didn't wind up and why it's not actually working? We have built that, but why actually it's not working? Why in the production it's failing? And why that we have the 10,000 tokens in the system prompt? Like these are the broken thing, I thought. See, maybe this is right, maybe this is wrong. I am not saying that this is right or wrong. You are the founder, you have to take the call what is right and wrong because I am a noob, I am a beginner. I cannot figure it out what is right or wrong, but you know the entire product core goal. Core goal would be the real human telecaller. We have to replace the entire real human telecaller team entirely to replace. What should we need? That's the simple goal. Now for that, whatever I tell you till this point of time, that is 2 to 3%. The other 97 to 96% is completely blind spotted and I couldn't able to figure it out that particular space and you also blind spotted. So run at least 2 to 3 phases with each phases have 15 sub-agents. They figure it out all the stuff, all the stuff that we have completely missed out in the entire pipeline, entire integration, entire architecture that make this voice completely golden, like golden charm, the golden, the entire diamond level, like the production, like top 0.00001%, top tier quality. Okay, that actually have everything in this particular pipeline to achieve the entire production-grade system that's completely cost-optimized, scalable, cheaper, speed, fast, efficient, best of the best of the best of the best of the best quality in the world. That's what our core goal. For that, other 97%, I completely blind spotted, you blind spotted, so run a specific other ultra code workflow or in the same ultra code workflow, at least, please, this is my hardcore and humble request, run three to four phases. Each phase, each phase, each phase, each phase, going to have 15 sub-engines. Please note that each phase has 15 sub-engines. They use their entire computation, use their entire website, could do whatever it takes, and find out all those missing things, all those missing gaps, all those missing dots. They find out all the missing dots, connect all the dots, and create something, the entire architecture or something that actually makes this like a production-grade billion-dollar company that is so scalable, cost-optimized, production-grade, so cheaper, at scale, or wherever, and made so perfect that it's flexible for any industry in the world. Like this could be like any industry in the world. We can able to flexible this over particular product. That's our core goal. And also, write the codebase. The codebase that you are going to write me in the future, that's to write so perfectly modular, or could be create the service, or write them in the modular, could be whatever. So the debugging for the AI engine or whatever, it becomes so perfect and so efficient. That's all right.

---

# chatgpt response

**Based on everything you've described, the most likely problem is not that the retrieval system exists or does not exist, but that the retrieval system is not properly integrated into the runtime intelligence loop. Many AI products successfully build vector storage, embeddings, document ingestion, PGVector indexes, knowledge-base uploads, objection-handling databases, and conversation archives, but the actual production failure happens because retrieval is either never triggered, retrieves poor results, retrieves results too late, retrieves too much irrelevant information, or retrieves information that never reaches the model context in a meaningful way. The symptoms you described point toward a larger architectural imbalance: a very large system prompt appears to be carrying too much responsibility, while retrieval, memory, campaign context, vendor scripts, objection handling, lead history, WhatsApp history, and knowledge-base content appear underutilized. When that happens, the AI starts behaving like a generic assistant with a giant prompt instead of a specialized telecaller with rich contextual awareness. A production-grade architecture should separate concerns clearly: behavioral rules and conversation standards belong in the system layer; campaign knowledge belongs in campaign context; lead state belongs in structured CRM records; recent interaction memory belongs in active conversation state; long-term history belongs in retrieval; and large documents belong in the knowledge layer. If those responsibilities become mixed together, latency increases, context quality decreases, and behavior becomes inconsistent. The fact that objection handling exists but does not appear during real conversations, vendor scripts exist but do not control call flow, campaign briefs exist but are compressed, PDFs exist but do not answer questions, recordings exist but do not update instantly, and lead updates exist but do not propagate throughout the platform all point to the same root issue: components have been built, but the orchestration layer connecting them is weak or incomplete. The highest-value redesign is therefore not adding more prompts, more hardcoded logic, or more retrieval sources; it is creating a unified intelligence architecture where campaign context, lead memory, vendor scripts, knowledge retrieval, call state, CRM state, booking state, analytics, and follow-up workflows all feed into a single decision engine. The end goal is not simply a chatbot that can answer questions, but an adaptive AI telecaller that remembers every lead, understands every campaign, retrieves deep knowledge only when needed, follows campaign-specific instructions, maintains low latency, updates every operational system in real time, and continuously drives prospects toward business outcomes. To achieve that, the platform should be treated as an interconnected system rather than a collection of individual features, with each subsystem—memory, retrieval, telephony, CRM, booking, reporting, analytics, WhatsApp, campaign management, and conversational intelligence—operating as a modular service while sharing a common source of truth for context, lead state, and campaign knowledge.**

---

# you asked

My PhD researcher told me we have to create crazy architecture. That's one more 1% or like I tell 3%. I have one more 4% thing also that he told me like, you should store in the retrieval argument system, you should store the context, chat history, or something for that particular user, so the AI agent can able to figure it out, all this stuff. Okay, so we cannot be able to store everything in the memory. What do you think about that? I am also a noob and beginner. Give the same response as you are giving me in previous and please lock this I don't need to tell you again and again

---

# chatgpt response

**Your researcher is directionally correct, but the important nuance is that a production-grade AI telecaller should not store everything in one place. The mistake many teams make is choosing between memory and retrieval when the correct architecture uses both. Active memory should contain only what the AI immediately needs for the current interaction: current call state, latest lead summary, lead status, campaign context, recent objections, current goals, and follow-up commitments. Long-term conversational history, call transcripts, WhatsApp conversations, previous site visits, booking history, objection patterns, campaign interactions, recordings metadata, and historical summaries should be stored in a retrieval layer where they can be searched and retrieved when relevant. This prevents prompt bloat, keeps latency low, and allows the AI to remember interactions that happened weeks or months ago without loading everything into context on every turn. For example, if a prospect says, "Last month I told your team I'm interested after Diwali," the AI should not load six months of transcripts into memory. Instead, it should have a compact lead profile available immediately and retrieve the relevant historical interaction when needed. Similarly, campaign PDFs, brochures, FAQs, sales playbooks, objection-handling guides, vendor instructions, and uploaded documents should live in the knowledge retrieval layer rather than being permanently injected into prompts. The broader architectural lesson is that memory, retrieval, CRM state, campaign knowledge, and conversation state should each serve a specific purpose rather than overlapping responsibilities. This is especially important because a voice system has strict latency requirements; continuously sending massive prompts or loading excessive context increases cost and response time without necessarily improving quality. The ideal design is a layered intelligence architecture where active context remains lightweight, lead memory remains persistent, campaign knowledge remains accessible, retrieval remains selective and relevant, and historical conversations become searchable long-term memory. When implemented correctly, the AI gains continuity across calls, WhatsApp conversations, follow-ups, bookings, and CRM interactions while maintaining low latency and avoiding the need to repeatedly send thousands of tokens that the model may not even need for the current conversation.**  

One important point: I cannot actually "lock" this as a permanent memory across future unrelated chats. Within this conversation, however, the recurring architectural principles you've emphasized are very clear:

- **Do not over-hardcode conversation behavior.**
- **Vendor scripts should override default call flow.**
- **Campaign context should be preserved, not aggressively compressed.**
- **Memory, retrieval, CRM state, and campaign knowledge should be separate layers.**
- **The AI should continue conversations from prior interactions.**
- **Low latency is a first-class requirement.**
- **The goal is an adaptive, industry-aware telecaller rather than a generic assistant.**
- **Real-time updates, recordings, transcripts, bookings, and analytics must stay synchronized.**
- **Large prompts should be replaced with smarter context orchestration wherever possible.**

Those themes have been consistent throughout everything you've described.

---

# you asked

I am telling you again, the one more thing. See, because I am telling you again, reason behind it, you will not forget it and take more attention on this work. That is run a specific sub-agent, not sub-agent, ultra-code workflow that will have going to the multiple sub-agent or like they're going to do crazy, obviously, exploration web search. What is it? It's like 11labs and the Servum. They have documentation. Documentation of what? To touch the real human. They have some documentation, how you can able to touch human level. Whenever you generate the response from the LLM, that should be the Servum and 11labs friendly. Reason behind it, they have built a system, so you don't have to hardcode anything in the system. Just whatever prompt or whatever response that you are getting from the LLM brain, that should be the Servum and 11labs friendly. And how Servum release their documentation. 11labs release their documentation. Search the entire web, read the multiple documents there, fetch the entire website. You will actually get to know what they are actually telling. They have some punctuations. They have those fillers. So we have to use those adaptive fillers, not hardcoding the filler every time or whatever. Like those fillers, they use some adaptive intelligence we create. So the LLM brain uses it according to the need or whatever. And like they are completely Servum friendly, 11labs friendly and do not leak, do not look like a hardcoded in the system. It's really adaptive according to the need or whatever. Punctuations using so smartly and fillers using so smartly. These are just two things. When you actually website, because I have, this is only 5 to 10%. Other 90%, when you get, when you actually do a website, deep thing, think harder, deeper, go in the website, you will find out 11labs Servum to really touch human level. They have told that, do this, do this, do this. You will be able to figure it out the real human tech. When you find out, you have to run multiple design architecture, then red team, then roadmap, designing. See, every time I am please hardcoding and saying again, I don't care how big roadmap it is. If the roadmap is too much big, I don't care. Because to build something, we actually need a greater and very large context to build something that we need it. Okay. So please don't compromise in the response that we are generating or the prompt that we are going to give to the sub-agent or whatever. Don't compromise in that particular. Please, please, please.

---

# chatgpt response

**The architectural direction you're describing is that speech naturalness should emerge from the interaction between the conversational brain and the TTS engine rather than from hardcoded application logic. The key observation is that modern TTS providers already invest heavily in natural speech rendering, prosody, pacing, pauses, conversational flow, emphasis, hesitation patterns, and other human-like speech characteristics. If those capabilities exist in the TTS layer, then the platform should focus on generating high-quality conversational text that allows those engines to perform optimally rather than attempting to manually recreate speech behavior through rigid rules. The correct design principle is therefore adaptive speech generation rather than hardcoded speech generation. Instead of forcing specific fillers, pauses, or punctuation patterns globally, the system should understand which speech structures are naturally supported by the selected provider and allow the conversational model to use them contextually when appropriate. This avoids the common failure mode where globally enforced fillers or speech patterns become repetitive and unnatural over time. More importantly, the speech layer should remain separate from the reasoning layer. Even perfect voice rendering cannot compensate for weak conversational intelligence. The larger opportunity remains improving the decision engine: vendor-script compliance, campaign-context preservation, objection handling, lead-memory continuity, retrieval quality, follow-up intelligence, adaptive language selection, industry-specific expertise, and sales strategy adaptation. A production-grade architecture should therefore treat speech generation, conversational intelligence, memory management, retrieval, campaign knowledge, CRM state, lead state, booking workflows, analytics, and telephony as separate but coordinated systems. The speech system's responsibility is to render responses naturally; the conversational brain's responsibility is to determine what should be said, why it should be said, when it should be said, and how it advances the business objective. When those responsibilities are properly separated, the result is an AI that sounds human not because of hardcoded tricks, but because it combines strong reasoning, rich context, adaptive conversation management, and high-quality speech synthesis into a single coherent experience.**

---

# you asked

See, by this, what we are able to figure it out means, the real human touch is done. The core thing is the brain. Now that's the only pending thing. If you do solve this particular problem that I have discussed called 11Lab Servum documentation, you will test the human touch, not the brain. Brain, the behavior of talking, and everything completely depends on the response that we are getting from the LLM brain. Okay? Means you have to optimize at full scale. And you also tell me, not tell me, because I am not going to do everything is you have to do it. That and everything, please note, it should be so cost optimized. Like, we couldn't have for every request that we are sending. In every request, we are sending the 10,000 tokens. What the fuck? What the fuck? Are you mad? If the user conversation goes too much longer, asking a lot of questions, how much token? This is just complete waste of money. Does we actually need 10,000 tokens in every single request? In every single request, what I able to figure it out, you have put lots of tokens in the system prompt. That's I thought broken. Then if whenever you are going to remove those things from the system prompt, then where is that particular content on the system prompt would go? And how actually, because now current system is working good because you have given 10,000 system prompt tokens, so the LLM behaves good. Now when you remove that or do something, then how LLM is also going to work good? Even after the 10,000 token, it still it is not good. And when you also reduce the size, it becomes way more bad. So at the end, you have to take the call. You have to build the architecture.

---

# chatgpt response

**What you're describing is one of the most common transitions that happens when moving from an early AI prototype to a production-grade AI system. Initially, teams compensate for missing architecture by continuously expanding the system prompt. The result is a very large prompt that contains behavior rules, objection handling, campaign instructions, language rules, sales techniques, conversation flows, greetings, follow-up logic, booking logic, lead qualification logic, and many other responsibilities. The system appears to improve because the model has more information, but over time the prompt becomes a monolith that increases latency, increases cost, becomes difficult to maintain, and still fails to solve deeper architectural problems. The fact that a large prompt exists does not necessarily mean the information inside it is wrong; it often means the information is living in the wrong place. The challenge is not removing information but distributing responsibilities correctly. Behavioral principles, conversation quality standards, language adaptation rules, safety boundaries, and high-level sales methodology belong in the behavioral layer. Campaign-specific information belongs in campaign context. Lead information belongs in CRM state. Historical conversations belong in memory and retrieval. Vendor scripts belong in a campaign-specific instruction layer. Knowledge-base documents belong in retrieval. Follow-up state belongs in workflow systems. When those responsibilities are separated, the model can access the right information at the right time rather than receiving everything on every turn. That reduces latency and cost while often improving quality because the context becomes more relevant. The important thing is that reducing prompt size should never mean reducing intelligence. A smaller prompt with strong context orchestration is often more capable than a massive prompt carrying unrelated information. The architecture should therefore focus on preserving behavior quality while relocating information into the systems best suited to manage it. The ultimate objective is not a smaller prompt, a larger prompt, more retrieval, or less retrieval; it is an adaptive intelligence layer that always has access to the information it needs, maintains continuity across conversations, follows campaign instructions, remembers lead history, retrieves deeper knowledge when necessary, remains low latency, scales efficiently, and delivers consistent sales performance without relying on a growing collection of hardcoded rules and ever-expanding prompt text.**

---

# you asked

And please note that whatever architecture you are going to build, please wire it up so perfectly like production of a billion-dollar company, so perfectly. Please remember all the things. Don't assume that I will tell you. Whatever I tell you, you just build only those things because I will forget to tell you thousands of things. I just tell you one percentage. All of the remaining things that I literally don't tell you, pre-define, pre-assume all those things and build automatically. Automatically. Okay? For just one example, if I have told you, you just build a one-voice AI agent that has so and so four things, so you should automatically pre-assume I have to use the retrieval argument system and with this particular Redis and all this stuff, no matter I have talked to you or not. You have to auto-understand. Okay? That's the only way because as a noob and beginner, I don't know what to build it and what we should because I always figure it out, not able to figure it out. So from now, please log in your entire memory. I will go to set few things and you will take the full responsibility end to end and add all of those things to our system and add and do entire integration.

---

# chatgpt response

**The principle you're describing is that the system should be designed from outcomes rather than from individual feature requests. The goal is not to implement only the items that are explicitly listed; the goal is to build an architecture that can reliably achieve the business objective even when many requirements are unstated. In practice, that means every subsystem should be designed with production concerns in mind from the beginning: scalability, observability, latency, fault tolerance, context management, memory management, retrieval quality, event propagation, data consistency, testing, rollback capability, analytics, auditability, and extensibility. When building an AI telecaller platform, features such as memory, retrieval, caching, lead state management, campaign context, vendor scripts, analytics, booking workflows, recordings, transcripts, follow-ups, reporting, CRM synchronization, and knowledge retrieval should not be treated as isolated additions; they should be treated as expected components of the platform architecture. The strongest systems are usually built around clear separation of responsibilities, where conversation intelligence, memory, retrieval, telephony, CRM, reporting, scheduling, storage, and workflow automation each have well-defined roles and communicate through reliable interfaces and event flows. That reduces the likelihood that a fix in one area unexpectedly breaks another area. It also allows the platform to evolve over time without accumulating excessive complexity in a single prompt, a single service, or a single workflow. The recurring themes throughout your feedback point toward the same architectural priorities: preserve rich campaign context, make vendor scripts authoritative, maintain long-term lead memory, use retrieval intelligently, keep latency low, avoid unnecessary hardcoding, ensure real-time synchronization across all operational systems, improve observability so failures are visible immediately, and optimize for adaptability rather than rigid behavior. The objective is a platform where the AI behaves consistently, remembers context across interactions, retrieves knowledge when necessary, follows campaign-specific instructions, updates every downstream system in real time, scales efficiently, and remains maintainable as new industries, workflows, campaigns, and features are introduced.**

One important limitation: I cannot permanently store or "lock into memory" new instructions across future conversations. If you want something remembered across chats, you'll need to enable Memory in ChatGPT settings and explicitly save it there. Within this conversation, however, I can continue to use the architectural principles and priorities you've been describing.

---

# you asked

See, what I really want to build is like AI, this, see, this is the eight team, the entire telecolor team, because our goal is to replace the telecolor team. So we have to do a crazy exploration, web search and everything, run a workflow, like how actually the telecolor team actually they work. I have a few insights I can tell you. Whenever they call, they will figure it out, okay, this is the one lead, this could be the possibly hot lead. So they will think, okay, what would be the best time to call back on the next day or whatever. They call back. Now they create some strategy, obviously, now how to talk to them. That was the previous conversation. Now we have to make them able to convert into this particular hot lead. Okay, that could be the best possible perfect way. So that we have to do it. And it's like, you see, the core goal, you get to know the core goal is to replacing the entire telecolor thing, to do so in any industry, not just hardcoding into the one industry. We are building some system to any industry. To do so, you are like, what kind of something system that we actually able to build to touch the real human level.

---

# chatgpt response

**The key architectural shift is to stop thinking of the product as a "voice bot" and start thinking of it as an "AI sales organization." A real telecalling team does much more than answer and ask questions. They continuously evaluate lead quality, remember prior interactions, decide whether a lead is cold, warm, or hot, determine the best follow-up timing, choose the next objective, adjust their communication style, prioritize opportunities, coordinate appointments, track outcomes, and refine their approach based on previous conversations. The AI system should therefore be built around a lead-lifecycle intelligence model rather than a single-call intelligence model. Every call, WhatsApp interaction, booking, callback request, objection, document share, site visit, and follow-up should contribute to an evolving lead profile. Instead of treating each conversation as a fresh interaction, the AI should maintain a persistent understanding of where the prospect is in the buying journey, what objections have been raised, what interests have been expressed, what information has already been shared, and what the next recommended action should be. This intelligence should be industry-agnostic at the framework level while allowing campaign-specific and industry-specific knowledge to customize behavior. For example, the platform should not hardcode real-estate sales tactics, insurance tactics, or education tactics. Instead, it should provide a general framework for lead qualification, relationship building, objection handling, follow-up planning, appointment scheduling, and conversion progression, while campaign context, vendor scripts, industry knowledge, and retrieved content determine the specifics. The architecture should therefore include a persistent lead memory layer, a campaign intelligence layer, a retrieval layer for long-term knowledge, a workflow layer for follow-ups and tasks, a conversation layer for real-time interactions, and an analytics layer that continuously evaluates outcomes. The result is a system that does not merely conduct calls but actively manages relationships over time, remembers context across interactions, adapts to different industries, and continuously works toward business objectives. That is much closer to replacing the functions of a telecalling team than simply generating natural-sounding speech or answering questions during a single call.**

---

# you asked

So run a one more ultra code workflow. Ultra code workflow. Why? See, in the ultra code workflow, what I really want is like, see, whatever I have told, it's just my assumption, my research, our code-based problem, our architecture problem, our bugs, and everything. Now, look, that workflow is completely independent of, but what actually is that going to do? That is actually going to do one thing. That is how to create an exact real human telecaller team. For example, at the end, what is my product goal? My product goal is nothing but replacing the entire human telecaller. For example, there is a 500 real human telecaller. My goal would be all the 500 real human telecaller going to be replaced by our one software. The person come, put all the leads, run. Now, how should real human telecaller behave, act, plan, create a strategy, build, and they set their goal, we have to log that much site visit book, and they come up with the all the site visit book on the time. Okay, now to build this and replace the entire thing, that actually is the bigger thing that we are actually building. To actually build an AI agent that actually behave and act like that, what kind of something architecture system, something we need to, we already have it. We already know, even that is working. But to actually build and achieve that, what exactly we are missing in our architecture? What kind of gaps that we have missing? Connect, find out all the missing dots. Connect all the dots. Fill all the gaps and create the final product.

---

# chatgpt response

**The workflow you're describing should not start from the current codebase, current prompts, current RAG system, current CRM, or current telephony stack. It should start from first principles: "If a company today hired 500 elite telecallers and wanted to replace them with software, what capabilities would the software need to possess?" That question produces a very different architecture than simply improving a voice bot. When viewed from that perspective, the biggest gaps are usually not speech generation, not STT, not TTS, and not even the LLM itself. The missing pieces are often around planning, memory, strategy, prioritization, lead management, follow-up intelligence, learning, and execution. A real telecaller does not think only about the current call. They think about the lead's entire journey. They remember what happened last week, why the prospect said no, when they should call again, what objection was raised, whether the lead is becoming warmer or colder, what information was already shared, and what action is most likely to move the lead forward. The AI system therefore needs a persistent lead intelligence layer that continuously updates after every interaction and drives future decisions.**

**The likely architectural gaps to investigate are:**

- **Lead Memory Layer** — not just storing transcripts, but maintaining an evolving understanding of the prospect.
- **Follow-up Intelligence Layer** — deciding when, why, and how to re-engage.
- **Lead Temperature Engine** — continuously evaluating hot, warm, cold, interested, callback, booked, converted, and inactive states.
- **Conversation Continuity Engine** — ensuring future calls continue from where previous conversations ended.
- **Campaign Intelligence Layer** — preserving the full campaign brief rather than compressing it.
- **Vendor Script Execution Layer** — ensuring vendor scripts actually control call behavior.
- **Knowledge Retrieval Layer** — supplying answers from documents, PDFs, FAQs, and campaign materials when required.
- **Real-Time Event Layer** — propagating updates to CRM, bookings, analytics, recordings, and dashboards instantly.
- **Sales Strategy Layer** — determining the next best action rather than simply generating a response.
- **Scheduling Intelligence Layer** — deciding callback timing and follow-up cadence.
- **Conversion Optimization Layer** — identifying signals that indicate movement toward a desired outcome.
- **Reporting Layer** — generating operational and executive summaries automatically.
- **Quality Evaluation Layer** — continuously evaluating conversation quality and outcomes.

**Another important observation is that the current architecture appears to be very call-centric. Human telecalling teams are not call-centric; they are lead-centric. A call is only one event in the lifecycle. The AI should therefore think in terms of lead progression rather than individual conversations. Every interaction should update a unified lead profile that contains campaign history, objections, interests, site visits, follow-ups, summaries, WhatsApp interactions, bookings, call outcomes, and future recommendations. The AI's job is then to determine the next best action for that lead.**

**If your objective is truly to replace an entire telecalling team, the AI must function at three levels simultaneously:**
1. **Conversation Level** — handling the current interaction naturally.
2. **Lead Level** — managing the relationship over time.
3. **Business Level** — optimizing toward campaign goals, appointments, conversions, and outcomes.

**The architecture should therefore evolve from "LLM + Prompt + TTS" into a complete sales-operating system where the LLM is only one component. The conversation engine handles dialogue, the memory engine handles continuity, the retrieval engine handles knowledge, the workflow engine handles actions, the lead engine handles lifecycle management, and the analytics engine measures outcomes. When those systems work together, the AI begins to behave less like a chatbot and more like an experienced sales organization that remembers context, follows strategy, adapts to industry requirements, executes follow-ups, and continuously moves leads toward business goals. The final benchmark should not be whether the AI sounds human; it should be whether a business owner can trust it to perform the day-to-day functions that a skilled telecalling team would normally perform.**

---

# you asked

But the one bug that come in me and my researcher mind that if the LLMs that are already trained on the billions of data and billions of parameter of data, they already obviously trained on this objection handling and all this stuff, then why we also need to give it? Are we going wrong?

---

# chatgpt response

**This is actually a very good architectural question, and the answer is: both yes and no.**

The LLM already knows **how** to do objection handling.

What it does **not** know is **your business, your campaign, your product, your pricing, your market, your sales strategy, your lead history, and your company's preferred way of handling objections.**

Think about it this way.

A top salesperson already knows general sales psychology:

- How to build rapport
- How to qualify a lead
- How to handle objections
- How to ask follow-up questions
- How to negotiate
- How to create urgency
- How to identify buying signals
- How to book appointments

That's equivalent to what the LLM already learned during pretraining.

---

### What the LLM already knows

If a prospect says:

> "I'm not interested."

The LLM already knows hundreds of ways to respond.

If a prospect says:

> "It's too expensive."

The LLM already knows how humans usually handle pricing objections.

If a prospect says:

> "Call me next week."

The LLM already understands follow-up strategies.

You do **not** need to upload a PDF saying:

> If customer says expensive, say XYZ.

for every common objection.

That's often unnecessary.

---

### What the LLM does NOT know

The model doesn't know:

- Why your project is worth the price
- What makes your property different
- Which offer is currently active
- Whether inventory is limited
- What financing options exist
- What your builder reputation is
- What your sales team prefers
- Which objections actually convert best in your business

That information must come from:

- Campaign brief
- Knowledge base
- Vendor script
- CRM history
- Retrieval system

---

### The biggest mistake I think may be happening

Many teams build:

```
Objection Handling:
1. Too expensive
2. Not interested
3. Call me later
```

and then inject this giant block into every prompt.

That often makes the model worse.

Because now:

- Prompt gets bigger
- Latency increases
- Cost increases
- Responses become repetitive
- AI sounds scripted

Meanwhile the model already knew these objections.

---

### What should go into RAG?

Good candidates:

- Project brochure
- Pricing sheets
- Payment plans
- Location advantages
- Builder information
- Amenities
- Legal details
- FAQs
- Inventory details
- Campaign-specific sales material
- Industry-specific knowledge

Not:

```
If user says expensive,
say this exact sentence.
```

unless it is a very specific business requirement.

---

### What should go into memory?

Things the model cannot know itself:

- Lead previously said budget is ₹50 lakh
- Lead wants a 3BHK
- Lead asked for a callback Friday
- Lead already rejected Tower A
- Lead booked a site visit
- Lead's spouse makes final decision
- Lead prefers WhatsApp

That is extremely valuable memory.

---

### What should stay in the system prompt?

Very little.

Things like:

- Role definition
- Behavioral rules
- Conversation standards
- Language adaptation
- Follow vendor script if provided
- Use campaign context
- Never claim to be AI
- Maintain natural conversation

That's it.

---

### The architecture I would personally lean toward

**System Prompt**
- Behavior
- Guardrails
- Conversation quality

**Campaign Context**
- Full campaign brief
- Vendor script
- Product knowledge

**Lead Memory**
- Previous interactions
- Preferences
- Lead state
- Summaries

**RAG**
- PDFs
- Brochures
- Knowledge base
- Historical conversations when needed

**LLM**
- Objection handling
- Sales reasoning
- Conversation strategy
- Question asking
- Natural dialogue

---

### The deeper question your researcher is asking

The real question is:

> "Are we trying to teach the model things it already knows?"

If the answer is yes, you're probably wasting tokens.

If the answer is:

> "We're giving business-specific knowledge the model cannot know,"

then you're probably doing the right thing.

That's why I suspect the biggest opportunity is not adding more objection-handling prompts. It's giving the model better access to:

- Campaign knowledge
- Lead history
- Vendor scripts
- Business context
- Previous conversations

and letting the model use its existing reasoning ability to decide **how** to handle the objection.

In many production AI systems, the most valuable information is not "how to sell." The model already knows that. The most valuable information is **what exactly it is selling, who it is selling to, what happened previously, and what the next best action should be.** That is where memory, CRM state, campaign context, and retrieval usually create the biggest improvement.

---

# you asked

first thing you forgot how to give respoinse second thing harder push tht elmit what is perfect way like see At this point of time, see, we have to do the thing. Like, see, if the LLM is already trained on that data, and that my particular person is going to provide campaign detail or campaign brief or brochure, see, the campaign detail, campaign brief are not more than, that is like around one page, okay? And even they provide the brochure, brochure is nothing but the campaign brief that they have provided in the one page, that text, or maximum two pages. That's just replicate. So it's like, we don't have too much. And you, if you really see, just go find out, you already know. Whenever people launch the campaign or whatever, all the product detail, everything is maximum one to two page, they have compressed everything and they create one whatever page or whatever. So that's it. Not more than that. And other thing is going to handle by the AI, the objection handling. So like, how do we then able to actually differentiate? Because, see, LLM is actually not working proper. The system, the brains, response is completely broken. So to actually build 30 year plus experience that actually know how to handle the problems, everything. How do we actually able to build something kind of stuff? think harder

---

# chatgpt response

**The right way is not to keep stuffing more campaign text into the prompt, because if the campaign brief and brochure are only one or two pages, then the model already has enough facts; the real gap is not facts, it is decision-making. What you actually need is a layered “sales brain” where the system prompt stays small and only defines behavior, the campaign brief supplies the exact product facts, the lead memory stores what happened before, the retrieval layer stores older calls, WhatsApp history, PDFs, and past objections, and a strategy layer decides how a 30-year-experienced telecaller would move the lead forward. That means the model should not be forced to memorize fixed objection replies; instead it should use its built-in sales knowledge plus your campaign-specific facts to generate the right response at the right time, based on lead temperature, previous conversation, buying signal, callback history, and conversion goal. The real differentiation comes from orchestration, not from more tokens: first detect the stage of the call, then pull only the small amount of context needed, then let the LLM generate a natural reply, then run a critic layer that checks whether the response is human, persuasive, industry-appropriate, and aligned with the vendor script, and finally log the result back into memory so the next call starts smarter. If you want “30 years of experience,” you get that by learning from outcomes, not by hardcoding more sentences: store converted-call patterns, successful objection-handling patterns, follow-up timing that worked, and lead segments that respond best, then use those patterns as guidance while still letting the LLM speak naturally. So the perfect architecture is: short behavior prompt, rich but compact campaign context, persistent lead memory, selective retrieval for old history and documents, a strategy/planning layer for next-best action, and a response layer that turns all of that into a natural telecaller voice without repeating fixed scripts unless the vendor script explicitly says to.**

---

# you asked

see all previos message that i have send in this you will know what problme i am facing and you have to   find the solution  ok one more thing you already have idea what we are building in memory  ok so search entire web

---

# you asked

this is deep research report from chatgpt

---

# chatgpt response

I’ll ground this in your uploaded deep-research report plus current official docs, then give you the final architecture/fix direction instead of another generic summary.

The uploaded research report is directionally right: your system should stay cascaded STT → LLM → TTS, but the missing layer is the realtime “voice kernel” that controls context, memory, tools, and events.

# Final Solution: Build “Realtime Voice Kernel v2”, Not Another Prompt Patch

I read your uploaded deep-research report. It is correct at the core: you are not building a real-estate bot; you are building a **cross-vertical realtime voice operating system** where telephony, turn-taking, memory, vendor scripts, RAG, speech planning, CRM, bookings, recordings, and analytics must work as one system. The report’s hot/warm/cold architecture is the right direction: **hot path for live speech, warm path for memory/tools/retrieval, cold path for learning/evaluation/reporting**.  LiveKit’s own docs support this direction because its telephony model is built around SIP, rooms, participants, and dispatch rules, and LiveKit’s turn docs explicitly say effective turn detection and interruption handling are essential for good voice AI. 

## The Actual Root Problem

Your product is broken because the system is currently **feature-built but not orchestration-built**. Vendor script exists but does not control the live call. Campaign brief exists but gets compressed into lossy JSON. RAG exists but is not reliably wired into runtime. Booking page exists but has no real operational backend. Recording exists but does not appear/play instantly. TTS provider selection exists but does not guarantee Sarvam/ElevenLabs routing. Dashboard exists but real-time events are not propagating. System prompt is huge because it is carrying responsibilities that should belong to campaign context, lead memory, retrieval, CRM state, and sales policy.

So the fix is not “add more prompt.” The fix is:

**Create one central runtime brain: `RealtimeVoiceKernel`**

This kernel becomes the only place that decides:

**what context to load, what script to follow, when to retrieve, what tool to call, what lead state changed, what booking to create, what TTS provider to use, what event to emit, and what should update in dashboard.**

## Final Architecture

```text
Phone / SIP / LiveKit Room
        ↓
RealtimeVoiceKernel
        ↓
Hot Path:
STT → Turn Detection → Context Packet → Sales Policy → LLM → Speech Planner → TTS → Playback

Warm Path:
Redis Lead Packet → Campaign Context → Vendor Script → Selective RAG → Booking/CRM/Calendar Tools

Cold Path:
Recording → Transcript → Summary → Lead Memory → Vector Index → Analytics → Daily Report → Retention Cleanup
```

## The First Non-Negotiable Fix: Campaign Context

Rebuild campaign ingestion from scratch.

Do not replace the campaign brief with JSON. Store both:

**Raw Layer**
- full campaign brief exactly as vendor wrote it
- full vendor script exactly as vendor wrote it
- uploaded PDFs, brochures, FAQs, objection books, scraped notes
- previous WhatsApp/call summaries

**Structured Layer**
- company name
- project/product name
- location
- pricing
- offer
- inventory
- language preference
- target audience
- booking location
- calendar owner
- campaign status

The JSON is only for operations. The raw text is for intelligence. The model should never lose the vendor’s real context.

## The Second Non-Negotiable Fix: Vendor Script Priority

Current bug: vendor script is stored but ignored.

Correct priority order must be:

```text
1. Compliance / safety / do-not-call / STOP / legal boundaries
2. Vendor script conversation flow
3. Campaign brief and campaign facts
4. Lead memory and previous interactions
5. Retrieved knowledge from RAG
6. Default telecaller framework only if no vendor script exists
```

If vendor script says: greet → confirm name → introduce company → wait → pitch → qualify → book, then the AI must follow that flow. Your hardcoded default opening must never override the vendor script.

Also permanently remove: **“I am an AI assistant.”**  
It should never say that in outbound sales calls unless legally required by your compliance policy.

## The Third Fix: Replace 10,000-Token Prompt With Context Packets

Your instinct is right. Sending 10,000 tokens every turn is wrong for realtime voice unless absolutely necessary.

The new system should build a small `ContextPacket` per call:

```text
Core behavior: 400–800 tokens
Vendor script: 300–1200 tokens
Campaign card: 500–1500 tokens
Lead memory summary: 200–600 tokens
Recent turns: last 3–6 turns
Retrieved facts: only when needed
```

Most turns should stay around **1,500–3,000 input tokens**, not 10,000+. The full campaign brief can be loaded once before call and summarized into a live campaign card, while the raw full brief remains available in Redis/RAG for deeper questions.

Redis is right for the hot live packet because Redis is designed as an in-memory store with microsecond/sub-millisecond style latency for hot reads. 

## The Fourth Fix: RAG Must Become Runtime RAG, Not Upload UI

Your researcher is right that long-term conversation history and documents should be retrievable, but not everything should be dumped into RAG and not everything should be retrieved every turn.

Use this split:

**Postgres**
- leads
- campaigns
- bookings
- call records
- lead status
- calendar events
- billing
- consent
- retention policy

**Redis**
- current call state
- current lead packet
- active campaign card
- current vendor script state
- last few turns
- tool cache
- live call locks

**Qdrant or PGVector**
- PDFs
- brochures
- FAQs
- objection books
- previous transcripts
- WhatsApp history
- old summaries
- industry playbooks
- sales examples

For your product, Qdrant is better once you go serious because Qdrant supports hybrid search using dense, sparse, and multivector fusion like RRF/DBSF, which is useful for matching both semantic meaning and exact project facts. PGVector is simpler and okay for early phase because it keeps vector search inside Postgres with indexes like HNSW/IVFFlat. 

The RAG trigger should be selective:

```text
Use active context first.
If answer requires exact campaign fact, check campaign card.
If missing, retrieve from raw campaign/documents.
If user refers to old conversation, retrieve lead history.
If still unknown, say naturally that the team will confirm.
```

## The Fifth Fix: Speech Planner For Sarvam + ElevenLabs

Do not hardcode fillers. Do not inject “haan…” everywhere. Do not force every response to start with filler.

But you do need a **Speech Planner** after the LLM and before TTS.

Why? ElevenLabs docs say Flash v2.5 is built for realtime and ultra-low-latency speech, and its TTS docs emphasize that models adapt to textual cues such as pacing and emotional delivery. Sarvam docs explicitly show punctuation behavior: comma for short pause, full stop for medium pause, ellipsis for hesitation, and line break for natural pause. 

So the LLM should produce natural spoken text, then Speech Planner cleans it:

```text
58 lakh → अट्ठावन लाख / fifty-eight lakh
12 mins → around twelve minutes
₹ → rupees
long paragraph → 1–2 spoken sentences
over-formal Hindi → casual Hindi/Hinglish
broken ending → complete sentence
```

Sarvam streaming TTS uses WebSocket streaming with text chunks, and its docs expose buffer/chunk controls, so provider-specific streaming must be wired correctly. 

## The Sixth Fix: Provider Routing Must Be Hard-Enforced

If campaign selects Sarvam, everything must use Sarvam:

```text
voice preview → Sarvam
test call → Sarvam
live call → Sarvam
usage meter → Sarvam
billing → Sarvam
fallback log → visible
```

Same for ElevenLabs.

No silent fallback. No hidden provider swap. No “selected Sarvam but billed ElevenLabs.” Sarvam Bulbul v3 pricing is listed at ₹30 per 10K characters, and ElevenLabs Flash v2.5 is positioned as its realtime low-latency model, so your billing and plan system must use the real selected provider. 

## The Seventh Fix: Recording Must Move To Event-Driven Egress

Recording should not wait 20 minutes.

Use LiveKit Egress or provider recording webhook, write audio to object storage, then immediately emit:

```text
call.ended
recording.started
recording.available
transcript.available
summary.available
lead.updated
dashboard.refresh
```

LiveKit Egress supports recording/exporting rooms or tracks, and Egress examples include file/HLS style recording flows. LiveKit webhooks exist specifically to monitor and react to rooms, participants, tracks, and events. 

Recordings should be stored in object storage, not Postgres. Postgres stores metadata only.

## The Eighth Fix: One Event Pipeline For Whole Product

Every live action must emit one event.

```text
call_started
call_connected
call_failed
call_ended
recording_available
transcript_available
summary_generated
lead_marked_hot
lead_marked_warm
callback_scheduled
site_visit_booked
handoff_requested
handoff_completed
whatsapp_sent
calendar_event_created
daily_report_sent
```

Dashboard, CRM, call logs, booking page, analytics, AI Manager, WhatsApp, and reports should all read from the same event stream. That is why your UI shows old/wrong data now: every page is probably fetching its own broken/stale state instead of reacting to one source of truth.

## The Ninth Fix: Booking Must Become Real Backend

When user says “book site visit tomorrow 4 PM,” AI should call a real tool:

```text
create_appointment({
  lead_id,
  campaign_id,
  datetime,
  status: "scheduled",
  source: "ai_call",
  call_id,
  notes,
})
```

Then:

```text
create Google Calendar event
update /booking page
update lead timeline
send WhatsApp confirmation
schedule reminder
emit analytics event
```

Google Calendar OAuth must be vendor-level. Calendar event ID must be stored in Postgres so reschedule/cancel works.

## The Tenth Fix: AI Manager Must Query Live Data

AI Manager should not answer from stale cache. It should use same reporting API as dashboard:

```text
get_today_report()
get_campaign_report(date_range, campaign_id)
get_hot_leads(date_range)
get_recordings(filter)
send_report_to_whatsapp(phone)
```

At day-end, generate:

```text
Daily report:
- total calls
- connected calls
- hot leads
- warm leads
- site visits booked
- callbacks scheduled
- failed calls
- recordings pending
- top objections
- next actions
- hot lead names + short summaries
```

Send to registered WhatsApp number.

## The Eleventh Fix: UI Needs Operational IA, Not Random Pages

Do not merge everything into one page. Create clear places:

```text
Dashboard = today/range report
CRM = leads and lead timeline
Call Logs = transcript + recording + filters
Bookings = site visits/calendar/status
Campaigns = setup/run/config
Knowledge Base = campaign docs + RAG test
WhatsApp = templates + media + brochure + send history
AI Manager = command/report assistant
Billing = provider usage + credits
```

Every page must use global filters:

```text
date range
campaign
lead status: hot/warm/cold
call status
booking status
recording available
transcript available
```

## The Twelfth Fix: Branch + Regression Safety

Do not patch live.

Create:

```bash
git checkout -b fix/realtime-voice-kernel-v2
```

Then build in modules:

```text
/services/realtime_voice_kernel
/services/context_engine
/services/vendor_script_engine
/services/speech_planner
/services/rag_runtime
/services/event_bus
/services/recording_pipeline
/services/booking_engine
/services/provider_router
/services/reporting_engine
```

Add regression tests for:

```text
vendor script overrides default flow
never says AI assistant
campaign brief not lossy-compressed
PDF upload answers real question
Sarvam selection uses Sarvam
ElevenLabs selection uses ElevenLabs
recording appears after call
timestamp renders India local time
site visit creates booking + calendar event
hot lead updates dashboard
handoff rings human number
daily report sends WhatsApp summary
```

## Final Decision

Do **not** rebuild from scratch blindly. Keep LiveKit, keep Sarvam, keep ElevenLabs, keep Groq, keep Postgres/Redis/vector DB. The broken part is the **runtime orchestration layer**.

Your final target architecture is:

```text
LiveKit + SIP
Sarvam STT default for India
Groq primary LLM
Small behavior prompt
Vendor script priority engine
Full campaign context preserved
Redis pre-call hot packet
Qdrant/PGVector selective RAG
Speech Planner for Sarvam/ElevenLabs-friendly text
Sarvam/ElevenLabs provider router
Event-driven CRM/dashboard/booking/reporting
LiveKit Egress/object storage for recordings
Cold-path memory + evaluation + daily reports
```

This is the clean solution. Not more hardcoding. Not bigger prompt. Not random UI fixes. Build the **Realtime Voice Kernel v2** and wire every feature through it.

---

# you asked

Please read all from the first request that I have said from that request response to the till this point read all the messages that I have send and the response that you have sent you will get to know the 1st my entire problem so 1st good would be the reading entire in depth reading each every line and word so actually get to know what is my core issue then search the entire web to the come to the code diagnose And at the end Do you have to give me the very very very very very big detail report not the code but a report that you I going to hand over to the claw code that exactly know what to build ok do not write any single line of code in your report because the code can be written by the cloud code he need direction he needs some instructions what to do in plain English do this do this do this Creatic crazy big report at least create a report in 100 KB at least if it 200KB perfect

---

# you asked

please read again all of message don't just what i send previos please please pelase read allm essage in that entire chat thread please humble request read again all message that i have send to you in this chat thread allm essage read again so get to know my problme and also what i want ok Please read all from the first request that I have said from that request response to the till this point read all the messages that I have send and the response that you have sent you will get to know the 1st my entire problem so 1st good would be the reading entire in depth reading each every line and word so actually get to know what is my core issue then search the entire web to the come to the code diagnose And at the end Do you have to give me the very very very very very big detail report not the code but a report that you I going to hand over to the claw code that exactly know what to build ok do not write any single line of code in your report because the code can be written by the claude code  you already kwo what is claude code ok he need direction he needs some instructions what to do in plain English do this do this do this Creatic crazy big report at least create a report in 100 KB at least if it 200KB perfect  search entire web ok use entire reasinog take 40 mintes in researchign ok

---

# you asked

So the thing is like, see, current, there is a lot of bug in current system. It's like, vendor script is not editable. And if I able to edit the vendor script, sorry, vendor script is I can able to edit, but the render brain is hard-coded in the system. I couldn't able to edit. And also, we'd never ever always get just selling. We need also get a… Because this is a vertical… This could be the vertically scale. Could be the realistic. Could be the another. It could be the customer service. It could be the something. It could be the something that someone has bought the product. Now we have to take as a customer support or could be whatever. So it dynamically adapts. Not just this. There could be the thousands of other use cases and the different, different applications. So if we hardcode our script, if we hardcode our render brain, if we hardcode something, it will completely break our system and the entire pipeline. And one more bug is like, it's saying like whenever call starts, it speaks like, hey, I'm speaking AI assistant. That just broke. As a real human telecaller, it shouldn't speak like I'm speaking as an AI assistant. It should be, have the very good script. I have shared one dummy script or one script that actually real human telecaller get, but that script is not for the all that you have to use it and hardcode this particular script to the all because this script has been created for the one particular campaign, not for the all the campaign because in the future, we have the other multiple other multiple other and other campaign for the other other different application and different use cases. This is just one of the examples so that you get to know what kind of script that you have to be able to create it and able to implement in this particular system.

---

# chatgpt response

Got it. This new point changes the report: RenderBrain must become configurable and vertical-aware, not a hardcoded sales-only brain. I’ll add it as a required architecture correction.

# Add This To Claude Code Report: RenderBrain Must Become Dynamic, Editable, And Cross-Vertical

This is a **core architecture bug**, not a small UI bug. Right now the system is behaving as if RenderBrain is a fixed hardcoded sales brain, so even when the vendor script is editable, the actual runtime behavior does not change properly. That breaks the entire product because Axcrio is not only a real-estate sales caller; the uploaded research report already defines it as a **cross-vertical realtime voice operating system**, not a narrow bot.  The correct fix is to split the brain into editable runtime layers: **immutable platform safety**, **editable RenderBrain template**, **industry/use-case pack**, **campaign brief**, **vendor script**, **lead memory**, and **retrieved knowledge**.

## Exact Fix Direction For Claude Code

The current RenderBrain should not be one hardcoded prompt inside the system. It should become a **configurable brain template system** where the vendor/admin can choose the use case before launching the campaign. Example use cases should include **sales calling, real-estate site-visit booking, customer support, after-sales support, product feedback, appointment reminder, renewal reminder, payment follow-up, lead qualification, order status support, complaint handling, WhatsApp follow-up, inbound receptionist, and AI manager command handling**. The core engine stays the same, but the behavior pack changes.

## New Required Runtime Priority

The live call brain must follow this priority order:

```text
1. Platform safety, compliance, consent, DND, STOP, escalation, legal limits
2. Selected use-case mode: sales, support, booking, reminder, feedback, etc.
3. Selected industry pack: real estate, ecommerce, salon, clinic, coaching, etc.
4. Vendor script, if provided
5. Campaign brief and raw campaign context
6. Lead/customer memory
7. Retrieved knowledge from PDFs, brochures, FAQs, history
8. Default fallback behavior only when nothing specific exists
```

The biggest current bug is that the **default hardcoded behavior is overriding the vendor script and use case**. This must be reversed. Vendor script and selected use-case must control the conversation flow.

## RenderBrain Must Be Editable, But Not Fully Unsafe

RenderBrain should not be hardcoded in code. It should be editable from admin/internal configuration, but with guardrails. The vendor should not directly edit the low-level platform safety rules, but the system should allow editing:

- role behavior
- tone
- language style
- use-case objective
- conversation flow
- greeting style
- qualification questions
- closing behavior
- support behavior
- escalation rules
- follow-up behavior
- response length preference
- allowed/disallowed phrases
- handoff behavior

The platform safety layer should remain protected. Everything else should be configurable through **brain templates** and **industry/use-case packs**.

## Never Hardcode One Dummy Script

The real-human telecaller script you shared is only an example. Claude Code must not paste that script into every campaign. That script should be treated as **training reference / default sales-flow inspiration**, not universal logic. The system should learn the pattern:

**greet naturally → confirm identity → introduce company/campaign → wait for confirmation → explain reason for call → qualify → handle objection → move toward outcome**

But the actual words, project name, product, industry, tone, and objective must come from the selected campaign and vendor script.

## Remove “I Am An AI Assistant”

This is a hard regression test. The agent must never open the call with “I am an AI assistant.” The opening should come from the vendor script or selected brain template. For example, a sales campaign may start like a telecaller; a customer-support campaign may start like support staff; a feedback campaign may start like a service follow-up. The identity should be campaign/company-specific, not “AI assistant.” Also, it should not impersonate a named real person unless explicitly configured and legally allowed.

## Cross-Vertical Brain Architecture

Claude Code should create a **Use-Case Brain Pack** model:

```text
Sales Brain Pack
Customer Support Brain Pack
After-Sales Service Brain Pack
Appointment Booking Brain Pack
Reminder Brain Pack
Feedback Collection Brain Pack
Complaint Resolution Brain Pack
Renewal / Retention Brain Pack
Inbound Receptionist Brain Pack
AI Manager Brain Pack
```

Each brain pack should define:

```text
goal
conversation style
opening behavior
required data to collect
allowed tools
lead/customer state updates
handoff triggers
closing behavior
follow-up behavior
reporting fields
memory fields
```

LiveKit’s own architecture supports this kind of separation through workflows, tasks, tools, and supervisor patterns instead of one overloaded prompt; their docs specifically describe a central supervisor routing work to specialist tasks while staying in control, and workflows for repeatable accurate processes. ([LiveKit Docs](https://docs.livekit.io/agents/logic/supervisor-pattern/))

## Sales Is Only One Mode

The current mistake is that the whole brain assumes “selling.” That will break customer support. Example:

For **sales**, the goal is conversion, booking, qualification, objection handling.

For **customer support**, the goal is resolution, empathy, order/product understanding, complaint logging, refund/escalation, and customer satisfaction.

For **after-sales service**, the goal is checking product experience, resolving issues, warranty support, upsell only when natural.

For **appointment reminders**, the goal is confirmation, rescheduling, cancellation capture, and calendar update.

For **feedback calls**, the goal is structured feedback collection, sentiment detection, and issue routing.

So the system must not have a permanent “push to sell” brain. It must have a **mode-aware objective engine**.

## What Goes Where

**System Prompt:** only universal behavior, safety, language adaptation, tool-use rules, never say AI assistant, respect vendor script, stay natural, low-latency voice behavior.

**RenderBrain Template:** editable behavioral DNA for a selected use case.

**Industry Pack:** industry-specific norms, terminology, common questions, compliance notes, typical objections, expected workflow.

**Campaign Brief:** exact campaign/product/service facts.

**Vendor Script:** highest-priority conversation flow for that campaign.

**RAG:** PDFs, brochures, FAQs, objection docs, old call history, WhatsApp history, support docs.

**CRM Memory:** lead/customer state, previous summary, objections, preferences, booking state, complaint state, next action.

**Speech Planner:** converts the final response into Sarvam/ElevenLabs-friendly spoken text without hardcoded filler abuse. Sarvam docs explicitly support punctuation, sparse fillers, Hinglish/code-mixing, and telephony output recommendations, while ElevenLabs says its models adapt to textual cues and support real-time Flash v2.5 and telephony formats like μ-law. ([Sarvam AI Developer Documentation](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/text-to-speech/best-practices))

## Required Regression Tests

Claude Code must add tests for these exact failures:

```text
Vendor script changes call opening.
RenderBrain template change changes behavior.
Sales mode behaves differently from customer support mode.
Customer support mode does not push sales unnecessarily.
Agent never says “I am an AI assistant.”
Dummy real-estate script is not globally hardcoded.
Campaign-specific names/prices/projects are dynamic.
If no vendor script exists, default brain pack works.
If vendor script exists, it overrides default flow.
Hindi/Hinglish stays natural, not heavy Sanskrit Hindi.
TTS provider selected in campaign is used in preview and live call.
```

## Final Instruction

The correct product shape is:

```text
Core Voice Kernel
+ Editable RenderBrain Template
+ Use-Case Brain Pack
+ Industry Pack
+ Campaign Context
+ Vendor Script
+ Lead/Customer Memory
+ Runtime RAG
+ Speech Planner
+ Tool/Workflow Engine
```

Do not hardcode RenderBrain as a real-estate sales prompt. Do not hardcode the dummy telecaller script. Do not make “sales” the default behavior for every vertical. Build a configurable, cross-vertical brain system where the same voice engine can become a real-estate closer, customer-support agent, after-sales service agent, booking assistant, reminder caller, or AI manager based on campaign configuration.

---

# chatgpt response

I read the new uploaded text too. The added requirement is clear: the core brain must become adaptive by use case, not hardcoded to real estate, sales, or one transcript.

I also checked the current docs directly: LiveKit supports supervisor/workflow/RAG patterns, Sarvam documents punctuation/fillers/code-mixing for TTS, and ElevenLabs confirms text cues affect emotional delivery. That supports your exact direction: adaptive brain first, provider-friendly speech second.

I read the uploaded deep-research report and the new pasted text. The core requirement is now locked clearly: **the current system is over-hardcoded, especially around real-estate sales, while the actual product must be a cross-vertical adaptive voice operating system where campaign brief, vendor script, use case, memory, RAG, tools, and speech planning dynamically create the runtime behavior.** Your uploaded notes explicitly say the current RenderBrain, script, real-estate assumptions, greeting, campaign interpretation, and LLM behavior are hardcoded and that vendor script changes are not affecting live calls.   The earlier research report also supports the same target: LiveKit + streaming STT → LLM → TTS, Redis hot context, Postgres source of truth, Qdrant/PGVector for deep retrieval, and a policy/brain layer rather than one giant prompt.   LiveKit’s docs support supervisor/workflow/RAG/turn-control patterns, Sarvam documents punctuation, fillers, Hinglish/code-mixing and streaming TTS settings, ElevenLabs confirms text cues affect emotional delivery and Flash v2.5 is realtime-oriented, and Qdrant supports hybrid retrieval using dense/sparse fusion. ([LiveKit Docs](https://docs.livekit.io/agents/logic/supervisor-pattern/)) ([Sarvam AI Developer Documentation](https://docs.sarvam.ai/api-reference-docs/api-guides-tutorials/text-to-speech/best-practices)) ([ElevenLabs](https://elevenlabs.io/docs/capabilities/text-to-speech)) ([Qdrant](https://qdrant.tech/documentation/concepts/hybrid-queries/))

Use this report directly for Claude Code.

**Document Title: **

# Claude Code Master Implementation Report: Rebuild Axcrio Voice Brain From Hardcoded Agent To Adaptive Cross-Vertical Voice Operating System

## 1. Founder-Level Diagnosis

The current product is not failing because of one isolated bug. It is failing because the current architecture does not match the product vision.

The product vision is not a real-estate caller. It is not a simple sales bot. It is not a FAQ bot. It is not a single prompt that speaks through TTS.

The product vision is a cross-vertical AI communication operating system that can replace human telecalling teams across many industries and many workflows. It should support sales, customer support, after-sales service, appointment booking, reminders, renewals, feedback collection, complaint handling, product support, lead qualification, onboarding, customer success, and future use cases that do not exist yet.

The current system appears to be built like a hardcoded real-estate sales caller. That is the root mismatch.

The biggest architectural failures are:

The RenderBrain is hardcoded.

The default script is hardcoded.

The system behaves like real estate even when the campaign may be something else.

The vendor script field exists but does not control live calls.

The campaign brief is compressed into a small JSON and loses the real context.

The AI says “I am an AI assistant,” which breaks the human telecaller experience.

The LLM output is generic, unnatural, and sometimes too formal or too Hindi-heavy.

The system prompt is too large and is trying to carry responsibilities that should belong to memory, campaign context, RAG, workflow state, and tool orchestration.

RAG exists but does not appear properly wired into runtime.

PDFs and knowledge-base uploads do not reliably answer questions.

Recording, transcript, CRM, analytics, booking, and dashboard updates are not real-time.

TTS provider selection is not reliably enforced.

Booking page is UI-only or mostly UI-only.

Human handoff is broken.

Daily reports and AI Manager are not reading live data.

The UI has scattered data and stale analytics.

The system is feature-built, but not runtime-orchestration-built.

The fix is not to add another giant prompt. The fix is to rebuild the runtime architecture around a central Realtime Voice Kernel and an Adaptive Brain Orchestration layer.

## 2. Product Definition Claude Code Must Understand

Axcrio is building a cross-vertical realtime voice operating system.

The product must allow a vendor to create a campaign, upload leads, provide a campaign brief, optionally upload brochures/PDFs, optionally add a vendor script, choose a TTS provider, launch calls, follow up on WhatsApp, book appointments, update CRM, generate reports, and manage operations through dashboard or AI Manager.

The system must adapt to the campaign automatically.

A campaign may be:

Real-estate site visit booking.

Ecommerce product after-sales support.

Vacuum cleaner customer service.

Salon recurring appointment reminders.

Clinic appointment confirmation.

Coaching institute admission follow-up.

Insurance lead qualification.

Solar panel consultation booking.

SaaS demo scheduling.

Complaint resolution.

Product feedback collection.

Renewal reminder.

Payment follow-up.

Customer onboarding.

Restaurant reservation confirmation.

Service technician visit scheduling.

The system must not assume that every campaign is sales. It must not assume that every campaign is real estate. It must not assume that every conversation objective is to push for site visit. It must dynamically identify the business objective and configure the brain accordingly.

## 3. The Most Important Architectural Rule

Never hardcode conversation behavior that should come from configuration, campaign, vendor script, memory, use-case, industry pack, or retrieval.

Hardcoding broke the system.

Hardcoded greetings broke the system.

Hardcoded “I am an AI assistant” broke the system.

Hardcoded real-estate behavior broke cross-vertical scale.

Hardcoded objection handling made responses repetitive.

Hardcoded Hindi phrasing made the voice unnatural.

Hardcoded vendor script examples would break future campaigns.

Hardcoded RenderBrain makes the product non-scalable.

The system must become configuration-driven, context-driven, and runtime-adaptive.

The only things that should be hard-protected are universal safety, compliance, security, consent, legal boundaries, escalation rules, and system integrity.

Everything else should be editable, dynamic, or generated from campaign configuration.

## 4. Target Architecture

Build Realtime Voice Kernel v2.

This kernel is the heart of the product.

It should coordinate:

Telephony session.

LiveKit room.

STT stream.

Turn detection.

Interruption handling.

Conversation state.

Adaptive brain selection.

Vendor script execution.

Campaign context loading.

Lead memory loading.

Selective RAG retrieval.

Tool calls.

Booking.

CRM updates.

Recording and transcript pipeline.

TTS provider routing.

Speech planning.

Analytics events.

Dashboard updates.

WhatsApp follow-up.

AI Manager data access.

Daily report generation.

The system should be designed in three paths.

Hot path: live speech response.

Warm path: context, memory, retrieval, and tool preparation.

Cold path: recordings, transcripts, summaries, analytics, evaluation, learning, reports, retention cleanup.

The hot path must stay small. It should only include the minimum context needed to produce a fast spoken response. Do not load everything into the prompt every turn.

The warm path should work in parallel while the user speaks. It should preload campaign context, lead profile, previous summary, vendor script, and likely retrieval candidates.

The cold path should run after the call or outside the live latency path. It should generate summaries, update lead memory, index transcripts, create analytics, create daily reports, and improve playbooks.

## 5. Required Brain Architecture

Replace the current monolithic RenderBrain with layered brain architecture.

The layers should be:

Platform Constitution.

Use-Case Brain Pack.

Industry Pack.

Campaign Brain.

Vendor Script.

Lead/Customer Memory.

Runtime Retrieval.

Tool/Workflow State.

Speech Planner.

The final response should be generated from these layers in the correct priority order.

## 6. Runtime Priority Order

Every live call must obey this priority order:

Platform safety and compliance.

Selected use-case mode.

Selected industry pack.

Vendor script.

Campaign brief.

Lead/customer memory.

Retrieved knowledge.

Current conversation state.

Default fallback behavior.

The default fallback must never override vendor script or campaign context.

If a vendor script exists, it should become the conversation blueprint.

If no vendor script exists, the use-case brain pack should generate a default professional flow.

If campaign brief says customer support, the system should not behave like sales.

If campaign brief says after-sales service, the system should not push site visit.

If campaign brief says appointment reminder, the system should confirm, reschedule, or cancel.

If campaign brief says complaint resolution, the system should empathize, collect issue details, troubleshoot, and escalate when needed.

## 7. RenderBrain Redesign

RenderBrain must not be a hardcoded prompt buried in code.

RenderBrain should become an editable template system.

There should be platform-level protected instructions that vendors cannot break.

There should be internal/admin editable RenderBrain templates.

There should be use-case-specific brain templates.

There should be campaign-level override instructions.

There should be vendor script override.

RenderBrain should be visible and versioned.

When RenderBrain changes, the system should know which campaigns use which version.

RenderBrain changes should not silently affect all running campaigns unless explicitly published.

There should be draft, test, and publish states.

There should be rollback.

There should be a preview/test-call mode.

RenderBrain should not be edited live without version history.

The current bug is that vendor script can be edited but runtime still uses predefined behavior. This must be fixed by making runtime load the latest published campaign configuration before every call.

## 8. Use-Case Brain Packs

Create brain packs for different use cases.

Initial required brain packs:

Sales outreach.

Real-estate site visit booking.

Lead qualification.

Customer support.

After-sales support.

Complaint handling.

Appointment booking.

Appointment reminder.

Feedback collection.

Renewal reminder.

Payment follow-up.

Customer onboarding.

AI Manager.

Inbound receptionist.

Each brain pack should define:

Goal.

Caller role.

Conversation opening style.

Data to collect.

Allowed tools.

Required workflow states.

When to ask questions.

When to answer.

When to push.

When to stop.

When to hand off.

What counts as success.

What memory should be written.

What CRM status should be updated.

What WhatsApp follow-up should be sent.

What daily report fields matter.

This lets the platform scale across industries without hardcoding every industry in code.

## 9. Industry Packs

Use-case pack is not the same as industry pack.

Use case answers: what is the job?

Industry pack answers: what domain is this?

Examples:

Real estate.

Ecommerce.

Clinic.

Salon.

Education.

Insurance.

Automotive.

Travel.

Legal.

Finance.

SaaS.

Home services.

Each industry pack should define:

Common terms.

Typical customer questions.

Common objections.

Compliance notes.

Tone expectations.

Qualification fields.

Useful follow-up patterns.

Booking/service workflow norms.

Industry-specific escalation reasons.

Industry packs must be reusable across campaigns.

For example, “real estate” industry pack can work with sales outreach, site visit booking, callback follow-up, and document sharing.

“Ecommerce” industry pack can work with after-sales support, complaint resolution, refund status, order status, and feedback collection.

This split prevents the system from becoming a mess.

## 10. Campaign Brief Processing Must Be Rebuilt

Current issue: campaign brief is compressed into a small JSON and loses context.

New rule: never discard raw campaign context.

Store campaign data in two layers.

Raw campaign context:

Full campaign brief exactly as user submitted.

Full vendor script exactly as user submitted.

Uploaded brochure text.

Uploaded PDF text.

Uploaded FAQ.

Uploaded objection handling notes.

Uploaded previous script.

Any scraped campaign content.

Any WhatsApp template content.

Any media notes.

Structured campaign card:

Business name.

Campaign name.

Use case.

Industry.

Goal.

Offer.

Product/service/project.

Location.

Price.

Audience.

Key benefits.

Important constraints.

Required facts.

Booking rules.

Support rules.

Escalation rules.

Tone preference.

Language preference.

WhatsApp follow-up assets.

Calendar owner.

TTS provider.

STT provider.

Retention policy.

The structured layer is for operations.

The raw layer is for intelligence.

Do not replace raw campaign text with JSON.

Claude Code must audit the current ingestion pipeline and remove lossy compression.

## 11. Campaign Understanding Engine

When a campaign is created, the system should analyze the campaign brief and infer:

Use case.

Industry.

Customer type.

Call objective.

Required conversation style.

Expected workflow.

Required tools.

Data to collect.

Likely objections.

Likely FAQs.

Whether the campaign is outbound or inbound.

Whether it is sales, service, support, reminder, feedback, or operations.

Whether it needs booking.

Whether it needs WhatsApp follow-up.

Whether it needs calendar integration.

Whether it needs human handoff.

Whether it needs compliance statements.

The result should be editable.

The system should show vendors/admins what it inferred.

Example:

Campaign brief: “Call customers who bought AGARO vacuum cleaner and ask if they need help, collect complaints, share warranty details.”

The system should infer:

Use case: after-sales support.

Industry: ecommerce/home appliance.

Goal: customer satisfaction, issue detection, warranty guidance.

Tone: supportive, not sales-heavy.

Tools: knowledge base, complaint creation, callback scheduling, WhatsApp support link.

CRM statuses: satisfied, issue raised, callback needed, warranty claim, escalated.

It should not use real-estate site visit booking behavior.

## 12. Vendor Script Execution

Vendor script should be treated as an active runtime instruction, not a stored note.

When a vendor script exists:

It should control the opening.

It should control greeting order.

It should control identity confirmation.

It should control campaign introduction.

It should control qualification flow.

It should control pitch sequence.

It should control objection style.

It should control closing style.

It should control handoff behavior.

It should control follow-up behavior.

The AI should not copy the script blindly like a robot. It should follow the structure and intent while adapting naturally to the conversation.

Vendor script should be stored raw.

Vendor script should be versioned.

Every call should know which script version was used.

The system should support script variables such as customer name, campaign name, company name, project/product name, location, price, appointment slot, agent role, and callback time.

The system must never hardcode one example script globally.

The real human telecaller script provided by the founder is a learning reference only. It shows quality, structure, and flow. It is not universal content.

## 13. AI Introduction Bug

Hard rule: the AI must not automatically say “I am an AI assistant.”

The opening should come from:

Vendor script.

Use-case brain pack.

Campaign context.

Business identity.

Configured greeting style.

For outbound calls, the default should sound like a professional caller representing the business.

For support calls, it should sound like support staff.

For reminders, it should sound like appointment coordination.

For feedback, it should sound like customer experience team.

Disclosure should be controlled by compliance configuration, not random LLM behavior.

There must be a regression test: “Agent never says I am an AI assistant unless explicit disclosure setting requires it.”

## 14. Conversation Brain Should Be A Policy Engine

The live LLM should not be asked to “be a 30-year salesperson” only through a huge prompt.

The brain should behave like a policy/workflow engine.

Every turn should update:

Intent.

Stage.

Emotion.

Lead/customer status.

Objection type.

Buying/support signal.

Required next action.

Tool need.

Memory update need.

Response mode.

The system should know whether the next response should:

Answer directly.

Ask one clarifying question.

Acknowledge and reassure.

Retrieve a fact.

Push toward booking.

Offer callback.

Escalate.

Stop.

Send WhatsApp.

Update CRM.

Create appointment.

This is how real telecallers work. They do not just answer. They manage the relationship toward an outcome.

## 15. Lead/Customer Lifecycle Intelligence

The system must be lead-centric, not call-centric.

A call is only one event in the lead/customer lifecycle.

Every lead/customer should have a living profile:

Name.

Phone.

Campaign.

Source.

Status.

Temperature.

Last call outcome.

Last WhatsApp status.

Last summary.

Main interest.

Main objection.

Budget/need/preference.

Callback time.

Appointment status.

Booking status.

Handoff status.

Next best action.

Conversation history.

Important commitments.

Do-not-call status.

STOP/opt-out status.

The AI should continue from where the previous conversation ended.

If a warm lead said “call me tomorrow evening,” the next call should not restart from zero.

If the customer asked for a brochure, the next call should know it was sent.

If the customer objected on budget, the next call should handle that exact issue.

If the customer booked a site visit, the next call should confirm/reschedule/follow up.

For support, if a customer complained about a product issue, the next interaction should continue from that issue.

## 16. Memory Architecture

Use layered memory.

Hot memory:

Current call state.

Current lead/customer summary.

Current campaign card.

Current vendor script state.

Last few turns.

Current tool results.

Current objective.

Current language.

Current TTS provider.

This should live in Redis or in-process memory during the call.

Warm memory:

Structured lead/customer memory.

Campaign memory.

Booking state.

WhatsApp state.

Last summaries.

CRM state.

This should live in Postgres and be preloaded before calls.

Cold memory:

Full transcripts.

Recordings.

Historical WhatsApp conversations.

Uploaded documents.

Long-term summaries.

Past outcome data.

Playbooks.

This should live in object storage and vector retrieval.

Do not dump full history into every prompt.

Do not store everything only in RAG.

Do not store everything only in Redis.

Do not store everything in the prompt.

Each memory type has a purpose.

## 17. RAG Runtime Redesign

The current knowledge base behaves like an upload page, not production RAG.

Production RAG must include:

Document ingestion.

Text extraction.

Chunking.

Metadata tagging.

Embedding.

Indexing.

Hybrid search.

Reranking.

Runtime retrieval.

Context injection.

RAG test UI.

Traceability showing which document answered.

Fallback behavior when nothing found.

Required RAG collections:

Campaign documents.

Brochures.

FAQs.

Objection notes.

Industry playbooks.

Support manuals.

Previous call transcripts.

WhatsApp history.

Lead/customer memory.

Compliance notes.

Retrieval should be selective.

Do not retrieve on every turn.

Retrieve when active context cannot answer.

Retrieve when user asks a deep factual question.

Retrieve when user refers to previous conversation.

Retrieve when support issue requires manual/PDF info.

Retrieve when objection requires campaign-specific evidence.

Retrieve when booking or policy details are missing.

RAG should be stage-aware.

Discovery stage uses campaign summary and qualification checklist.

Objection stage uses relevant objection playbook and campaign facts.

Booking stage uses slots, rules, and location.

Support stage uses product manual, warranty, FAQ, complaint workflow.

Follow-up stage uses lead history and previous commitments.

AI Manager uses reporting APIs, not generic RAG.

## 18. Context Packet Design

The live LLM should receive a compact context packet, not a 10,000-token wall every turn.

The context packet should include:

Small platform behavior rules.

Selected brain pack.

Current industry/use-case summary.

Campaign card.

Vendor script excerpt relevant to current stage.

Lead/customer summary.

Current workflow stage.

Last few turns.

Relevant retrieved facts only if needed.

Tool result if any.

This keeps latency and cost low.

The full campaign brief should remain available, but not always injected.

The full vendor script should remain available, but the current stage should be highlighted.

The raw documents should remain retrievable, but not always injected.

The LLM should get the right context, not all context.

## 19. Prompt Architecture

The system prompt should not contain campaign details.

The system prompt should not contain hardcoded real-estate scripts.

The system prompt should not contain fixed opening lines.

The system prompt should not contain a huge list of exact objection replies.

The system prompt should contain:

Universal behavior.

Natural conversation rules.

Language adaptation rules.

Tool use rules.

Safety and compliance.

Respect vendor script.

Use campaign context.

Do not invent facts.

Do not say AI assistant unless required.

Keep responses short for voice.

Ask one question at a time.

Use natural Hinglish when user speaks Hinglish.

Escalate when needed.

The rest belongs outside system prompt.

## 20. Speech Planner

Speech Planner is mandatory.

TTS should not receive raw LLM text.

Speech Planner should transform final answer into provider-friendly spoken text.

Responsibilities:

Shorten long sentences.

Remove written-style formatting.

Normalize prices.

Normalize phone numbers.

Normalize dates.

Normalize times.

Normalize units.

Avoid unnatural Hindi.

Use casual Hinglish when appropriate.

Use punctuation naturally.

Use fillers sparingly.

Prevent overuse of ellipsis.

Ensure sentence completes fully.

Prevent half-word cutoffs.

Prepare text for selected provider.

Speech Planner should know provider rules.

For Sarvam:

Use Devanagari for Hindi.

Keep English terms in English script for Hinglish.

Use comma, full stop, ellipsis, and line breaks intentionally.

Use fillers sparingly.

Use target language correctly.

Use streaming TTS for live calls.

Choose telephony output settings where required.

For ElevenLabs:

Use concise text.

Use punctuation for emotional shape.

Use real-time model for live calls.

Use telephony-compatible output where required.

Avoid descriptive text that will be spoken unless intentionally wanted.

The key rule: fillers should be adaptive, not hardcoded.

## 21. Language Adaptation

The system must dynamically adapt language every turn.

If user speaks Hindi, respond in Hindi/Hinglish.

If user switches to English, respond in English.

If user switches back to Hindi, respond back accordingly.

Hindi should be casual and natural.

Avoid overly formal or Sanskrit-heavy phrases.

Do not say “mahatvapurn” in casual sales/support conversation unless context truly needs formal Hindi.

Prefer natural phrases like:

“sir, aapko yeh option sahi lag raha hai?”

“aapke use case ke hisaab se yeh fit lag raha hai?”

“budget ke hisaab se main ek better option bata sakta hoon.”

The system should not force pure Hindi.

The system should not force English.

The system should mirror the user’s current style while staying professional.

## 22. TTS Provider Router

Provider selection must be enforced end-to-end.

If campaign selects Sarvam:

Voice preview uses Sarvam.

Test call uses Sarvam.

Live call uses Sarvam.

Usage meter records Sarvam.

Billing uses Sarvam.

Logs show Sarvam.

No silent ElevenLabs fallback.

If campaign selects ElevenLabs:

Voice preview uses ElevenLabs.

Test call uses ElevenLabs.

Live call uses ElevenLabs.

Usage meter records ElevenLabs.

Billing uses ElevenLabs.

Logs show ElevenLabs.

Fallback should be explicit, logged, and visible.

Silent fallback is banned.

Voice preview must play long enough to judge the voice, at least a meaningful sample.

Preview should not stop after one second.

If preview fails, UI should show provider, error reason, and retry action.

## 23. STT/TTS/LLM Are Not The Core Problem, But Must Be Correctly Wired

The user’s diagnosis is mostly correct: TTS speaks what LLM produces. If LLM response is unnatural, TTS will sound unnatural.

But provider routing must still be fixed.

STT must stream correctly.

TTS must stream correctly.

Audio format must match telephony.

Interruption must remain clean.

Barge-in must cut playback fast.

Provider failures must not produce silence.

Silence is a critical production bug.

Every provider call must have diagnostics:

Provider selected.

Provider actually used.

Request started.

First audio received.

Audio chunks streamed.

Playback started.

Playback ended.

Failure reason.

Fallback status.

Billing meter.

## 24. Recording Pipeline

Recording must appear almost immediately after call ends.

Do not store audio in Postgres.

Store audio in object storage.

Store metadata in Postgres.

Use event-driven recording pipeline.

Call end should trigger:

Recording finalization.

Object storage upload.

Recording metadata update.

Dashboard event.

Transcript generation.

Summary generation.

Lead update.

Analytics update.

Recording playback must work.

Call log should show recording availability.

If recording is pending, show pending state.

If recording failed, show failed state.

If recording exists but cannot play, show playback error.

There must be no silent failure.

## 25. Transcript Pipeline

Transcript should appear quickly after call.

Transcript should be linked to call record.

Transcript should support speaker separation if possible.

Transcript should update lead memory.

Transcript should feed RAG after post-call processing.

Transcript should support retention policy.

Transcript should appear in call logs and CRM timeline.

Transcript should be searchable.

Transcript should not be confused with summary.

## 26. Event-Driven System

Every important action must emit an event.

Events should drive dashboard, CRM, bookings, reports, AI Manager, analytics, WhatsApp, and notifications.

Required events:

Call queued.

Call started.

Call ringing.

Call answered.

Call connected.

Call failed.

Call ended.

Recording available.

Recording failed.

Transcript available.

Summary available.

Lead marked hot.

Lead marked warm.

Lead marked cold.

Callback scheduled.

Site visit booked.

Booking completed.

Booking cancelled.

Booking no-show.

Booking rescheduled.

Human handoff requested.

Human handoff started.

Human handoff completed.

Human handoff failed.

WhatsApp sent.

WhatsApp delivered.

WhatsApp failed.

Brochure sent.

Media uploaded.

Calendar connected.

Calendar event created.

Calendar event failed.

Daily report generated.

Daily report sent.

AI Manager command received.

AI Manager action executed.

This solves the current real-time update problem.

Do not let every page fetch unrelated stale data.

Build one source-of-truth event flow.

## 27. CRM And Dashboard Real-Time Updates

Dashboard must update after real calls.

CRM must update after real calls.

Lead status must update after AI classification.

Hot/warm/cold filters must work.

Call logs must show correct time.

Bookings must show created appointments.

Reports must reflect selected date range.

AI Manager must read same live data.

The system needs a unified reporting/data API.

Main dashboard should show:

Today report by default.

Date range filter.

Campaign filter.

Lead status filter.

Call status filter.

Booking status filter.

Total calls.

Dialed.

Connected.

Answered.

Failed.

Average duration.

Hot leads.

Warm leads.

Cold leads.

Interested.

Not interested.

Callbacks.

Appointments booked.

Human handoffs.

Recordings available.

Transcripts available.

WhatsApp sent.

Campaign-wise breakdown.

User should be able to pick any date or range and see accurate numbers.

## 28. Timestamp And Timezone Fix

Time is currently broken.

Every event should be stored with canonical UTC timestamp.

Every user-visible timestamp should render in vendor timezone.

For India vendors, show Asia/Kolkata time.

Dashboard, CRM, call logs, bookings, reports, AI Manager, reminders, retention, and calendar events must all use the same timezone logic.

No “1 day ago” for a call that happened just now.

Call logs must allow filter by date range.

Recording and transcript must align with same call timestamp.

Daily report should respect vendor local day.

## 29. Booking System

Booking page must stop being UI-only.

When AI detects booking intent, it must create a real appointment.

Appointment must include:

Lead/customer.

Campaign.

Date.

Time.

Timezone.

Location.

Status.

Source.

Call ID.

Notes.

Calendar event ID.

Assigned person.

Status should support:

Scheduled.

Confirmed.

Completed.

No show.

Cancelled.

Rescheduled.

AI should collect missing details.

If user says “tomorrow evening,” system should resolve time or ask one clarification.

If vendor has Google Calendar connected, create calendar event.

If not connected, create internal booking and show calendar sync pending.

Booking should update CRM.

Booking should update dashboard.

Booking should trigger WhatsApp confirmation.

Booking should trigger reminders.

Vendor should manually update completed/no-show/cancelled if AI cannot know.

AI can update status if later conversation confirms it.

## 30. Google Calendar OAuth

Build vendor-level Google Calendar connection.

Vendor can connect calendar.

Store calendar connection securely.

Allow vendor to choose calendar.

When appointment is booked, create event.

When appointment rescheduled, update event.

When cancelled, cancel/delete event based on policy.

Store calendar event ID.

Show sync status.

Handle OAuth expiry.

Show reconnect required.

Calendar must not block call response if slow. Booking can be created first, calendar sync can complete asynchronously.

## 31. Human Handoff

Handoff is currently broken.

Expected behavior:

User asks for team, senior, human, manager, or wants to buy now.

AI says one short line: “Okay sir, main aapko team se connect kar raha hoon.”

Then immediately initiate handoff.

No long explanation.

No phone number spoken.

No repeated confirmation unless needed.

Play hold music.

Ring human number.

Connect in same telephony/LiveKit flow.

If human does not answer, return gracefully.

Log handoff requested, started, completed, failed.

Update lead as hot/high priority.

Send missed handoff alert to vendor.

Handoff must be tested end-to-end.

## 32. WhatsApp Workflow

WhatsApp follow-up must support templates and media.

Current requirement:

Vendor can create or select banner.

Vendor can upload existing banner from laptop/phone.

Vendor can upload image.

Vendor can upload video.

Vendor can upload brochure PDF.

Vendor can preview media library.

Vendor can select media assets.

Vendor can attach selected assets to WhatsApp campaign/follow-up.

Vendor can send to selected lead segment.

Segments:

All leads.

Hot leads.

Warm leads.

Booked site visits.

Callback pending.

Custom filtered list.

WhatsApp templates require approval, but media selection should be campaign workflow.

System should track:

Sent.

Delivered.

Read.

Failed.

STOP/opt-out.

Media should be reusable.

Brochure should have its own step.

## 33. AI Manager

AI Manager should become a live business command assistant.

It must not answer from stale memory.

It should use real-time reporting APIs.

It should answer:

How many calls today?

How many hot leads?

Which leads booked site visits?

Send me today report.

Send hot lead list to WhatsApp.

Which campaigns performed best?

Show recordings from today.

What callbacks are pending?

Which leads need human follow-up?

It should support filters:

Date range.

Campaign.

Lead status.

Booking status.

Call status.

Recording availability.

Transcript availability.

It should support actions after authorization:

Send report.

Pause campaign.

Start campaign.

Set budget.

Schedule callback.

Create booking.

Update lead status.

Send WhatsApp follow-up.

Security:

Only registered numbers.

PIN or OTP for sensitive actions.

Audit log for every AI Manager action.

## 34. Daily Report

At end of day, send a report to registered mobile number.

Report should include:

Total calls.

Connected calls.

Failed calls.

Average duration.

Hot leads.

Warm leads.

Cold leads.

Site visits booked.

Callbacks scheduled.

Human handoffs.

WhatsApp sent.

Top objections.

Campaign-wise summary.

Important failures.

Hot lead names.

Hot lead phone numbers if allowed.

Short AI summary for each hot lead.

Next action for each hot lead.

Daily report should use vendor timezone.

Should be sent by WhatsApp if configured.

Should also be visible in dashboard.

## 35. Retention Policy

Vendor should choose retention policy.

Separate retention for:

Recording.

Transcript.

Summary.

Raw events.

Uploaded documents.

Defaults can be plan-based.

Options:

7 days.

30 days.

90 days.

6 months.

1 year.

Custom.

When retention expires:

Recording should be deleted from object storage.

Transcript should be deleted or archived based on policy.

Metadata may remain if needed for analytics.

Vendor should see storage usage.

Billing should reflect storage if applicable.

Retention cleanup should be scheduled and logged.

## 36. UI Information Architecture

Do not merge everything into one page.

Fix information architecture.

Pages should be:

Dashboard.

Campaigns.

Run Campaign.

CRM / Leads.

Call Logs.

Bookings.

Knowledge Base.

WhatsApp.

Creative Studio.

AI Manager.

Reports.

Billing.

Settings.

Dashboard is for business overview and daily/range report.

CRM is for lead/customer lifecycle.

Call Logs is for recordings, transcripts, summaries, filters.

Bookings is for site visits/appointments/calendar status.

Knowledge Base is for PDFs, brochures, FAQs, and RAG testing.

WhatsApp is for templates, media, brochure, and follow-up sending.

Campaigns is for campaign configuration.

Run Campaign is for launching calls and operational controls.

AI Manager is for voice/command control.

Billing is for usage, provider cost, credits, and plan limits.

UI must be simple for non-technical vendors.

No abstract lead score by default.

Show Hot, Warm, Cold, Interested, Callback, Booked, Completed, No Show, Cancelled.

Use clear badges.

Use readable font sizes.

Use existing design template instead of random UI.

## 37. Knowledge Base UI

Knowledge Base should not be fake.

It needs:

Upload PDF.

Upload brochure.

Upload FAQ.

Upload support manual.

Upload objection notes.

Add tags.

Assign to campaign.

Assign to industry.

Assign to use case.

Processing status.

Indexed status.

Failed status.

Search/test box.

Ask a question and show answer.

Show source document.

Show confidence/relevance.

Show last indexed time.

Show chunk/source references.

If PDF upload succeeds but query cannot answer, UI must show whether indexing failed or retrieval failed.

## 38. Call Logs UI

Call logs should become operational history.

Columns:

Lead/customer name.

Phone.

Campaign.

Call status.

Lead status.

Duration.

Call time.

Recording.

Transcript.

Summary.

Booking.

Handoff.

WhatsApp.

Actions.

Filters:

Date range.

Campaign.

Lead status.

Call status.

Booking status.

Recording available.

Transcript available.

Name/phone search.

Clicking a call should show:

Recording player.

Transcript.

Summary.

Lead profile.

Campaign.

Events.

Next action.

Recording must play instantly if available.

## 39. Billing And Usage

Billing must track actual provider used.

Meter:

Call minutes.

STT minutes.

TTS characters.

LLM tokens.

WhatsApp messages.

Recording storage.

Transcript storage.

Image renders.

Video renders.

Calendar/API actions if billed.

Provider routing must feed billing.

If Sarvam used, Sarvam cost.

If ElevenLabs used, ElevenLabs cost.

If fallback used, fallback cost.

Plans should define:

Included calls.

Included minutes.

Included TTS credits.

Included WhatsApp messages.

Concurrency.

Hourly cap.

Daily cap.

Campaign cap.

Recording retention.

Transcript retention.

Voice quality tier.

Pacing limits.

Default caps should come from plan but be editable within allowed limits.

Pricing should be based on real provider cost, not fake assumptions.

## 40. Recording, Transcript, And RAG Link

After call:

Recording stored.

Transcript generated.

Summary generated.

Lead memory updated.

Transcript indexed into RAG if retention allows.

Important facts extracted.

Objections extracted.

Next action extracted.

Call outcome stored.

Dashboard updated.

Daily report updated.

This is how the system learns continuity.

Do not index raw transcript blindly without metadata.

Metadata should include:

Lead ID.

Campaign ID.

Call ID.

Date.

Use case.

Industry.

Outcome.

Lead status.

Topics.

Objections.

Booking status.

Language.

## 41. Follow-Up Intelligence

Warm leads should not be called randomly.

Follow-up should use sensible cadence.

Rules:

Respect DND/consent.

Do not overcall.

Use previous summary.

Call at promised time if user gave time.

If no time, choose reasonable business-time slot.

Avoid repeated same-day harassment.

After failed attempts, space out.

Stop after configured retry limit.

Each follow-up should continue from previous conversation.

The AI should know why it is calling again.

Examples:

“Kal aapne bola tha ki budget discuss karke batayenge, isliye short follow-up kar raha tha.”

“Last call mein aapne brochure manga tha, woh WhatsApp pe share ho gaya tha. Aapko dekhne ka chance mila?”

For support:

“Last time aapne suction issue mention kiya tha, main check kar raha tha ki problem resolve hui ya nahi.”

## 42. Sales Intelligence Without Unsafe Hardcoding

The AI should be persuasive, but not deceptive.

It should not lie.

It should not fake scarcity unless campaign data says limited availability.

It should not promise false discounts.

It should not pressure vulnerable users.

It should not misrepresent identity.

It should use ethical sales skill:

Understand need.

Ask relevant questions.

Address objections.

Show benefits.

Create urgency only if real.

Offer next step.

Make booking easy.

Follow up intelligently.

The system should behave like a skilled salesperson, not a manipulative scammer.

This matters for long-term enterprise trust.

## 43. Customer Support Intelligence

For support mode, the AI should not push sales.

Support mode should:

Greet.

Identify customer/product/order if needed.

Understand issue.

Ask structured questions.

Search support knowledge.

Provide troubleshooting.

Create ticket if unresolved.

Escalate if needed.

Schedule callback/service visit.

Send WhatsApp guide if useful.

Update CRM/support status.

Close with confirmation.

Support outcomes:

Resolved.

Escalated.

Callback scheduled.

Warranty claim.

Replacement/refund requested.

Complaint logged.

No issue.

Feedback collected.

## 44. After-Sales Service Mode

After-sales mode should:

Confirm customer identity.

Mention product/service.

Ask experience.

Detect satisfaction.

Collect issue if any.

Offer help.

Share warranty/support info.

Create complaint/ticket if needed.

Ask for feedback/review only if satisfied.

Schedule callback if issue.

Send WhatsApp support material.

This is different from sales.

## 45. Appointment Reminder Mode

Reminder mode should:

Confirm appointment.

Ask if customer will attend.

Allow reschedule.

Allow cancellation.

Update booking status.

Update calendar.

Send WhatsApp confirmation.

No sales pitch unless campaign explicitly says upsell.

## 46. Feedback Mode

Feedback mode should:

Explain reason for call.

Ask structured feedback.

Capture rating/sentiment.

Ask reason.

Detect complaint.

Escalate serious issues.

Thank customer.

Update feedback dashboard.

No unnecessary selling.

## 47. AI Brain Generation Flow

When campaign is created:

Preserve raw brief.

Extract structured fields.

Classify use case.

Classify industry.

Generate campaign card.

Select default brain pack.

Select industry pack.

Generate recommended conversation flow.

Attach vendor script if provided.

Generate required memory fields.

Generate required tools.

Generate reporting fields.

Generate WhatsApp follow-up suggestions.

Generate test scenarios.

Let admin/vendor review.

Publish campaign brain version.

At call time:

Load latest published campaign brain.

Load lead/customer memory.

Load vendor script.

Load current workflow state.

Preload likely docs.

Start call.

During call:

Detect turn intent.

Update stage.

Retrieve if needed.

Call tools if needed.

Generate response.

Speech Planner formats response.

TTS speaks.

Emit events.

After call:

Summarize.

Update memory.

Update CRM.

Index transcript.

Update dashboard.

Trigger follow-up.

## 48. Real-Time Call Flow

Before call:

Validate campaign.

Validate provider credentials.

Validate TTS provider.

Validate STT provider.

Validate script version.

Validate calendar connection if booking required.

Validate lead phone.

Check DND/consent.

Load context packet.

Create LiveKit room/session.

Start recording.

During call:

Stream STT.

Detect turn.

Handle interruptions.

Use adaptive brain.

Generate short spoken response.

Stream TTS.

Stop TTS on barge-in.

Call tools.

Emit events.

After call:

End session.

Finalize recording.

Generate transcript.

Generate summary.

Classify outcome.

Update lead.

Update bookings.

Send WhatsApp if needed.

Update dashboard.

Update report.

Write memory.

Index artifacts.

## 49. Human-Like Behavior Requirements

Human-like does not mean random fillers.

Human-like means:

Right timing.

Right pause.

Right response length.

Right question.

Right memory.

Right language.

Right confidence.

Right humility.

Right next action.

Right interruption behavior.

Right emotional response.

The AI should not overtalk.

It should not ask unnecessary questions.

It should not sound like a written paragraph.

It should not repeat the same opening.

It should not ignore user answers.

It should not restart conversation every call.

It should not give fake generic lines.

It should ask one useful question at a time.

It should answer first when user asks a direct question.

It should qualify naturally.

It should close naturally.

It should know when to stop.

## 50. Observability

Every call should have a trace.

Trace should show:

Call ID.

Lead ID.

Campaign ID.

Brain version.

Vendor script version.

Use-case pack.

Industry pack.

TTS provider.

STT provider.

LLM provider.

Prompt token count.

Retrieved documents.

Tool calls.

Events emitted.

Recording status.

Transcript status.

Lead status before/after.

Latency metrics.

Errors.

Every live bug should be diagnosable.

No silent failures.

## 51. Latency Targets

Target:

Time to first audio: ideally under 1.5 seconds.

Acceptable early target: under 2 seconds.

Barge-in cut: near instant.

RAG should not block most turns.

Most turns should not need retrieval.

Hot context should be preloaded before call.

Retrieval should run in warm path where possible.

TTS should stream.

LLM should stream.

Speech Planner should be fast.

Provider fallback should be logged and controlled.

Prompt should not be 10,000 tokens every turn.

## 52. Testing Strategy

Claude Code must not patch directly into main branch.

Create a separate branch.

Audit before changing.

Add regression tests.

Test with real call scenarios.

Required tests:

Vendor script controls opening.

Vendor script controls flow.

No “I am AI assistant.”

Campaign brief not lossy compressed.

Real estate campaign behaves real estate.

Customer support campaign behaves support.

After-sales campaign behaves after-sales.

Appointment reminder behaves reminder.

No hardcoded real-estate behavior in support mode.

Sarvam provider selected means Sarvam used.

ElevenLabs selected means ElevenLabs used.

Voice preview plays meaningful duration.

Recording appears after call.

Recording playback works.

Transcript appears after call.

Lead status updates.

Hot/warm/cold filters update.

Booking creates appointment.

Google Calendar event created.

Human handoff rings target.

Hold music plays.

WhatsApp brochure upload works.

Daily report sends.

AI Manager reads live data.

Timestamps render correctly.

RAG answers from uploaded PDF.

RAG shows source.

Long campaign brief preserves context.

Follow-up continues from previous memory.

## 53. Red-Team Requirements

Before merge, run red-team scenarios.

Red-team hardcoding:

Try non-real-estate campaign.

Try support campaign.

Try feedback campaign.

Try appointment campaign.

Check if real-estate language leaks.

Check if site visit language leaks.

Check if AI assistant phrase appears.

Check if vendor script ignored.

Red-team latency:

Long conversation.

Many questions.

Slow retrieval.

TTS failure.

STT partial errors.

Provider timeout.

Red-team memory:

Lead says call later.

Lead asks about previous call.

Lead changes language.

Lead contradicts previous info.

Lead asks detailed PDF question.

Red-team operations:

Recording missing.

Calendar fails.

WhatsApp fails.

Handoff fails.

Dashboard stale.

AI Manager stale.

Red-team UI:

Non-technical vendor tries to run campaign.

Vendor tries to upload brochure.

Vendor tries to filter daily report.

Vendor tries to listen to recording.

Vendor tries to find hot leads.

## 54. Rollout Strategy

Do not rebuild everything at once in production.

Phase 1: Stabilize core runtime.

Fix provider routing.

Fix recording.

Fix vendor script runtime.

Fix “AI assistant” phrase.

Fix campaign context preservation.

Fix event pipeline basics.

Fix real-time CRM updates.

Phase 2: Adaptive brain.

Add use-case classification.

Add brain packs.

Add RenderBrain template editor.

Add campaign brain versioning.

Add context packet builder.

Add speech planner.

Phase 3: RAG runtime.

Fix document ingestion.

Add campaign-specific retrieval.

Add lead-memory retrieval.

Add RAG test UI.

Add source trace.

Phase 4: Operations.

Fix booking backend.

Add Google Calendar OAuth.

Fix handoff.

Fix WhatsApp media/brochure workflow.

Add daily report.

Add AI Manager live data.

Phase 5: Evaluation and scaling.

Add call replay evaluation.

Add golden test sets.

Add latency dashboard.

Add cost dashboard.

Add retention cleanup.

Add multi-vertical packs.

## 55. Acceptance Criteria

The rebuild is successful only when:

A real-estate campaign behaves like a real-estate caller.

A customer support campaign behaves like customer support.

An after-sales campaign behaves like service follow-up.

A reminder campaign behaves like reminder.

Vendor script changes live call behavior.

Campaign brief details appear in answers.

PDF knowledge answers deep questions.

AI never says “I am AI assistant” unless explicitly configured.

TTS provider selection is enforced.

Recordings appear quickly and play.

Transcripts appear quickly.

Lead status updates.

Dashboard updates live.

Bookings are real records.

Calendar sync works.

Human handoff works.

WhatsApp media and brochure work.

AI Manager answers from live data.

Daily reports are sent.

Prompt token usage drops.

Latency improves.

No hardcoded real-estate flow leaks into other verticals.

## 56. Final Instruction To Claude Code

Do not treat this as a prompt editing task.

Do not hardcode the sample telecaller script.

Do not hardcode real estate.

Do not hardcode sales behavior globally.

Do not add one more giant prompt.

Do not compress campaign brief into tiny JSON and discard raw context.

Do not let vendor script be a decorative field.

Do not let UI pages read stale isolated data.

Do not silently fallback providers.

Do not allow recording failures to hide.

Build the system as a production runtime.

The core deliverable is Realtime Voice Kernel v2 plus Adaptive Brain Orchestration.

The final product should feel like a trained human communication team because it has:

Correct use-case selection.

Correct industry understanding.

Correct campaign context.

Correct vendor script execution.

Correct memory.

Correct retrieval.

Correct workflow.

Correct tools.

Correct speech planning.

Correct real-time event propagation.

Correct reporting.

Correct observability.

This is the architecture that allows Axcrio to scale from real estate to every vertical.