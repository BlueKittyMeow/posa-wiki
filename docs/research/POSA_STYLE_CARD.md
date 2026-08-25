# Posa Style Card — v0 (DRAFT, awaiting Lara's edit)

*The "how Posa talks" document that ships inside the adjudicator packet.
Its job is to define the register in which a transcript sentence is judged
coherent, so that the coherence test never becomes a second smoothing pass
(TRANSCRIPT_VERIFICATION_DESIGN, amendment round 4).*

**Status:** v0, machine-drafted 2026-08-24 from validated evidence only
(`POSAISM_EXAMPLES.md`, ASR_SHOWDOWN §3/§7 human transcriptions, wiki entity
tables). Lara to edit — everything below is a candidate, not canon.

**Provenance rule for growth:** a line only enters this card once the claim is
backed by a human-validated transcript span or by Lara's direct description.
Model-inferred patterns do not get added.

---

## 1. Who is speaking

Matthew Posa, solo-to-camera in a canoe/boat or at a campsite, usually with a
dog present, often with no other human in frame. He narrates continuously to a
camera he treats as a companion, not an audience of strangers.

---

## 2. Register — the load-bearing facts

**He makes puns, and the pun is usually the point.** Episode titles are puns
and the pun gets said out loud in the episode. *Crap-Pie* (episode 15) is
literally the crappie/crap-pie joke: "we are targeting some **crap pie**, also
known as **crappie**." A transcript that renders both halves identically has
destroyed the joke, not cleaned up an error.

**He sings.** Original campfire songs, recurring and sequelised ("Chopping
Wood", "Still Chopping Wood"). Sung lines are not transcription noise.

**He mispronounces things on purpose.** "Blue sklies" for blue skies is a
recurring deliberate deformation. Odd phonology is a stylistic signature.

**He names objects and treats them as characters.** "Ronaldo The Unsplittable"
(a log). "The SS Tin Can 3.0" (a boat, versioned). Boats, logs, and gear get
proper nouns and personalities.

**He talks to his dog as a conversation partner**, mid-narration, without
marking the switch: "Say hi, Funk. Hi. Hah. Go get it, Monty." Second-person
imperatives and greetings addressed to a dog are normal sentences here, and
they interleave with camera-directed narration at speed.

**He opens with "Ladies and gentlemen."** Formal-address openings into
extremely informal content.

**He interrupts and restarts himself constantly.** "I caught like… seven?
crappies? ish?" — rising-uncertainty chains, self-hedging, and abandoned
clauses are how he actually speaks. A transcript of him should NOT read like
clean prose. Fluent, tidy sentences where the audio is messy are a symptom of
ASR smoothing.

**Recurring formulaic wisdom.** "Not too much salt, not too little salt, just
the right amount of salt." "Where there's downed trees there's fish and where
there's fish you'll catch 'em" — with silly variations. Repetitive,
sing-song, deliberately over-balanced constructions.

---

## 3. Domain lexicons

**Fishing:** crappie/crappies (the show's central word), bluegill/bluegills,
often shortened to "gills"; walleye, northern pike, panfish; jig, bobber,
leech, minnow, live bait; "steel eater" and similar real-but-odd angler terms —
**an unfamiliar fishing word is not evidence of a transcription error.**
Fish counts are given hesitantly and are frequently revised mid-sentence.

**Camping / bushcraft:** bushcraft, tarp, bivy, portage, canoe, paddle,
firesteel, tinder, kindling, batoning, splitting, hot tent, wood stove.

**Places:** Boundary Waters (BWCA), Northwoods, Minnesota/Wisconsin lakes.

**Show furniture:** "The Unsuccessful Fishing Show" and its inverted-logic
tagline ("if you're successful you're unsuccessful, and if you're unsuccessful
you're successful").

---

## 4. People and dogs

- **Matthew Posa** — the speaker. Rarely names himself.
- **Funk** — a real person (friend). ASR engines routinely hear "punk".
  Human-validated: in the *Crap-Pie* dog-play passage he says "Say hi, **Funk**."
- **Lucas, Erin, Jake, Ken**, and family (Mom, Dad, Brother) — recurring people.
- **Monty**, **Rueger**, **Layla** — the dogs. Monty is the constant companion.
- **Nicknames are invented on the fly and are not in any lexicon.** "Captain
  Teeny Trout" is a whole-episode nickname for an unnamed second angler; all
  three ASR engines render it wrong (Captain Trot / Captain Tea Truck /
  Captain T Truck). Expect nicknames; expect ASR to fail on them.

---

## 5. Instruction block for the judge

> You are ruling on what a human actually said, not on what a tidy sentence
> would be.
>
> 1. **Implausible is not evidence of error.** This speaker puns, sings,
>    mispronounces on purpose, names inanimate objects, and talks to his dog
>    mid-sentence. A reading that sounds silly may be exactly right.
> 2. **Never smooth wordplay.** If two witnesses disagree and one reading is a
>    pun, a rhyme, or a deliberate mispronunciation that fits the episode title
>    or the show's running jokes, that reading is *more* likely correct, not
>    less. Collapsing "crap pie, also known as crappie" into "crappie, also
>    known as crappie" is a transcription error, not a correction.
> 3. **Disfluency is signal.** Self-interruptions, "ish", trailing hedges, and
>    repeated words are how he speaks. Do not delete them and do not repair
>    them into grammatical sentences.
> 4. **Coherence is judged inside his register.** A sentence must read as
>    something *this* man would plausibly have said aloud, including to a dog.
>    Genuine incoherence — a sentence no one would utter, e.g. "Give me Can you
>    hear your little stinker" — IS evidence of transcription error.
> 5. **When you cannot tell, escalate.** Guessing a plausible replacement for
>    text that was already correct is the worst possible outcome. It is better
>    to escalate ten spans than to invent one.
