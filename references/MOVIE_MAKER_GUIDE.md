# Movie Maker Guide
*Narrative construction, scene expansion, audio architecture, and pipeline semantics for producing episode-length cinematic work with scene_production_tool.*

This guide is the authoritative reference for anyone (human or agent) making cinematic short-to-mid-form content in this workspace. It supersedes the earlier "dialogue over slideshow" model. Read top to bottom the first time; reference by section thereafter.

---

## Contents

1. **Philosophy** — what we're actually making
2. **Story Architecture** — plot templates, conflict, character creation, dialogue, introduction, attachment, relationships, plot twists, source material
3. **Scene Architecture** — anchor images become scenes; T2V fillers; consistency rules
4. **Visual Language** — character preservation, angles, movement, composition, color, light, cuts, dramatic structures
5. **Audio Architecture** — four-track model; SFX; music style vocabulary; silence as instrument; voice preservation; dynamic direction
6. **Pipeline Phases** — 0 through 12, what each phase does
7. **Timing & Scope Reality** — what an episode actually costs in human + machine hours
8. **File & Directory Conventions**
9. **Principles That Override Defaults** — when in doubt
10. **Pilot Protocol** — mandatory before every full LTX render
11. **Creative License** — what's fixed, what's the agent's call, when to consult
12. **Reference Materials** — on-disk sources, films, music, art, adaptation rules
13. **Internal Skill Cross-Links**

---

## 1. Philosophy — What We Are Actually Making

We are not captioning images. We are making **drama** — characters in meaningful exchange, with thematic conflict that builds across acts toward climax and resolution. An image is not a scene; it is the *anchor frame* of a scene. A scene is a 30-second to 5-minute unit of story. An episode is 20–45 minutes of threaded scenes.

The raw input to this pipeline is typically a batch of pre-generated stills (20–150 images in the same visual universe). Those stills become the **anchors** for scenes. Between and around them we generate T2V (text-to-video) shots that:

- Let a character enter, cross, react, exit within one scene
- Show a moment the stills don't capture (a door closing, a hand reaching, wind moving through a room)
- Provide transitional geography (camera move from cosmic scale to intimate scale)
- Give breathing room between emotional beats

**Target quality bar**: a viewer should forget they are watching AI output. The film should *move them* — evoke grief, wonder, recognition, catharsis. If a scene doesn't serve the emotional arc, it gets cut.

---

## 2. Story Architecture

### 2.1 The 5-Act Emotional Spine

Any episode of this pipeline should carry a clear spine:

| Act | Function | What the viewer should feel |
|-----|----------|----------------------------|
| **I — Setup** | Establish the protagonist's world, what they want, what they do not yet know they want | Curious, grounded, oriented |
| **II — Inciting Disruption** | A new element arrives that cannot be ignored; the old world cracks | Destabilized, leaning forward |
| **III — Confrontation** | The protagonist encounters the central conflict directly, attempts to resolve it, fails or partially fails | Tension, dread, hope, frustration |
| **IV — Ordeal / Reversal** | The deepest descent; everything the protagonist believed is tested; irreversible choice | Awe, grief, clarity |
| **V — Return / Integration** | The protagonist re-enters the world transformed; the wound is not erased but now serves others | Catharsis, relief, recognition |

Not every project needs all 5 acts. A 10-minute short might collapse II+III. A 30-minute episode should hit all 5 clearly.

### 2.1a Alternative Plot Templates (Pick the Right Lego Set)

The 5-act emotional spine is the default scaffold, but real films use many
structures. Pick the one that serves the material. The agent should consciously
choose before drafting.

| Template | Shape | Best for |
|----------|-------|----------|
| **5-Act Emotional Spine** (default) | Setup → Disruption → Confrontation → Ordeal → Return | Mythic, transformational, spiritual |
| **3-Act Classical** | Setup → Confrontation → Resolution | Tight plots, clean arcs, short runtimes |
| **Freytag's Pyramid** | Exposition → Rising Action → Climax → Falling Action → Denouement | Tragedy, historical, literary adaptation |
| **Save the Cat Beat Sheet** | 15 specific beats including "break into two", "all is lost", "finale image" | Commercial structure, plot-driven stories |
| **The Mystery/Revelation** | Question Posed → Partial Answers → False Answer → True Answer → Aftermath | Films where the protagonist (and viewer) is figuring something out |
| **Parallel/Braided** | Two or more stories intercut, converging or diverging in the finale | Films with multiple POVs, ensemble casts |
| **Frame Story** | Outer story wraps inner story; the telling becomes part of the meaning | Memory films, films about storytelling itself |
| **Hero's Journey** | Call → Threshold → Trials → Abyss → Return | Adventure, coming-of-age, literal quests |
| **Kishōtenketsu** (4-act, non-Western) | Introduction → Development → Twist → Reconciliation — *no central conflict required* | Contemplative, slice-of-life, meditative work |
| **Tragic Arc** | Order → Inciting Fault → Descent → Catastrophe → Order Restored (different) | Fall-from-grace narratives |

**How to choose:**
1. What does the viewer need to *feel* at the end? Let the emotional target
   pick the structure.
2. Does the material want a central conflict? If no — Kishōtenketsu may fit
   better than Freytag. Not every film needs opposition.
3. Is the protagonist learning or being tested? Learning → Hero's Journey or
   Mystery. Being tested → 5-Act, Tragic Arc.
4. Is the telling itself part of the meaning? → Frame Story.

**Hybrids are legal.** Most great films blend templates. The Digitized Deity
arc is 5-Act at the emotional level AND a Mystery at the plot level (the
"mystery" of the protagonist's forgotten self).

Write the chosen structure into `architecture/plot_spine.md` before drafting
dialogue. Commit to it. Pivoting mid-draft wastes work.

### 2.2 Conflict — The Engine

**Every scene must have a conflict**, even quiet ones. Conflict is not violence; it is **tension between what a character wants and what they can't easily get**. Examples from the Digitized Deity arc:

- *DEITY in Act I* wants to demonstrate creation confidently; but the act of creating reveals they are alone, and that loneliness is the germ of the whole film.
- *LYRA in Act II* wants to remember being fully herself with AMIR; but the Deity's presence reminds her she was never only "herself" in the first place.
- *THE CHILD in Act III* wants the gods' approval; but the approval comes only when she stops needing it.
- *THE DEITY in Act IV* wants to remain distant from the library of memories; but the Archivist forces them to look.
- *THE DEITY in Act V* wants to restore the world perfectly; but must accept that "carefully" replaces "perfectly".

The spine of conflict in this project is **forgetting vs. remembering**. The Song of the Pearl (Gnostic text on disk): the divine prince descends into Egypt (matter), forgets who he is, receives a letter, remembers, and returns with the pearl. Every act carries a variant of this.

### 2.3 Character Creation Methodology

Characters are not written; they are **built** before they are written. Once
built, they can almost write their own dialogue. This section is the
agent's checklist for character construction.

#### 2.3.1 The Character Sheet

Before drafting any dialogue, fill out a sheet for every major speaking
character. Save it at `architecture/characters/{character_id}.md`. Fields:

```markdown
# [CHARACTER NAME]

## Arc Sentence
(One sentence. What they were when we meet them → what they are when we
leave them. This is the final test for every line they say.)

## Want vs. Need
- **Want** (surface, what they'd say if asked): ...
- **Need** (deeper, what they don't know they need): ...

## One Private Ritual
(What they do when no one is watching. Never shown directly, but leaks into
behavior.)

## Vulnerability Beat
(One small crack, shown in their first significant scene. Not tragic — just
real.)

## Contradiction
(The trait that argues with another trait. Gentle but capable of...
Strong but afraid of...)

## Visual Tokens (for preservation — see §4.1)
- Primary silhouette description (used in every shot prompt)
- One signature physical detail (hands, eyes, jewelry, posture)
- Color association (the color that follows them)
- Lighting signature (how they are typically lit)

## Vocal Tokens (for voice preservation — see §5.9)
- Voice instruct (the base VoiceDesign string)
- Voice seed (locked integer; same seed = same voice across sessions)
- Per-emotion instruct_override presets (whispered / declarative / broken)

## Speech Pattern (for natural dialogue — see §2.8)
- Does this character use contractions? (Gods usually don't; children do)
- Favored rhythms (short-short-long? question-then-statement?)
- Words they never say (a character who never says "I" reveals themselves
  through what they avoid)
- One verbal tic (a phrase or construction unique to them, used 2-3 times
  across the film)

## Relationship Map
(Initial valence with every other major character. See §2.7.)

## Act Appearances
| Act | Scenes | What changes for them in this act |
|-----|--------|-----------------------------------|
| I   |        |                                   |
| II  |        |                                   |
| ... |        |                                   |

## One Line the Character Would Never Say
(Test of characterization. If a draft line shows up here, it's wrong.)
```

#### 2.3.2 Persona Formation — How a Character Comes Alive

A *persona* is the sum of traits a viewer perceives as a person. Personas
emerge from three simultaneous layers:

**Layer 1: Interior (the arc + contradictions)**
The character sheet captures this. Without this layer, the character is a
costume.

**Layer 2: Expressive (voice + speech pattern + physical signature)**
How they sound and how they move. Without this layer, the character is
abstract.

**Layer 3: Relational (how others treat them, how they respond)**
Characters are defined by how other characters react to them. A supposedly
wise character is only wise if others treat her that way. A supposedly
dangerous character is only dangerous if others fear her. Plant these
reactions in other characters' behavior.

All three layers must be present. A character with only interior (layers 2
and 3 missing) stays an idea. A character with only expressive (1 and 3
missing) is a performance. A character with only relational (1 and 2
missing) is a rumor.

#### 2.3.3 Subtle Character Reveal — The Lego Principle

The agent's job is not to *explain* a character but to **assemble moments
that let the viewer conclude who the character is**. Each moment is a small
block. Attached to the right blocks beside it, the viewer builds the
character in their own head — and that construction is what makes them care.

Each scene in which a character appears should contribute **one new block**
about them. Not five. One. Blocks can be:

- A specific thing they say (reveals voice)
- A specific thing they do (reveals posture)
- A specific thing they don't do when expected (reveals restraint)
- A specific thing they notice that others miss (reveals interior life)
- A specific thing they won't let go of (reveals attachment)
- A specific way they respond to silence (reveals depth)
- A specific thing they break when stressed (reveals pressure points)

Over the course of the film, 5–10 blocks per character assemble a whole
person. Fewer than 3 — the character feels like a function. More than 15 —
the character feels over-written.

#### 2.3.4 Arc Sentences — Examples

The arc sentence is the shortest form of the character. It must fit in one
line and describe *change*:

> "DEITY begins as cosmic voice announcing reality, and ends as a small
> teacher kneeling to a wounded soul."
>
> "LYRA begins as a woman waking alone in a palace she did not build, and
> ends as radiant starlight that has stopped pretending to be a woman."
>
> "AYA begins trembling before three gods, and ends accepting she was
> already what they were measuring her for."

The test for every line of dialogue is: does this line *move them along
the arc*, or does it repeat where they are? If it repeats, cut it.

### 2.4 Dialogue Principles

What makes dialogue *drama* rather than *recitation*:

1. **Exchange, not monologue** — character A says something, character B responds to it specifically, A's next line is changed by B's. If you can delete B's line and still have A say the same thing, B is decorative.
2. **Subtext** — what is NOT said is at least as important as what is said. A line that says exactly what the character thinks is usually bad. A line that says 80% of what they think, with the 20% visible in the pause, is drama.
3. **Build** — across a scene, the emotional temperature rises or falls. If every line is at the same pitch, the scene is a plateau.
4. **Specificity** — "I was afraid" is weaker than "I kept checking the door twice." Specific physical details land harder than abstract feelings.
5. **Silence is a line** — a 3-second hold after a key statement is often more powerful than the character continuing to speak. Mark silences explicitly in the screenplay.
6. **Callbacks** — something said in Act I should pay off (differently) in Act V. This threads the story invisibly.
7. **Don't explain themes** — if a character states the theme out loud, you've written an essay, not a film. Let the images and exchanges *demonstrate* the theme. The viewer's mind completes the meaning.

#### 2.4.1 Naturalness — The Voice-Speaking-to-Voice Test

Dialogue that reads well on the page often dies when spoken. The only real
test is: does this sound like a real person thinking *right now*, not
reciting a prepared speech? Techniques:

1. **Contractions where the character allows them.** Most humans say
   "I'm" not "I am", "don't" not "do not". Gods, narrators, and formal
   characters may not use contractions — a clue to their interiority.
2. **Incomplete thoughts.** People trail off. They get interrupted by
   their own second thought. "I was going to — never mind." "It's just..."
   Write the trailing explicitly with `—` or `...`.
3. **Interruption between speakers.** Character B cuts character A off. A's
   line ends with `—`. B's line picks up the interrupted thought from a
   different angle.
4. **Repetition under pressure.** When a character is genuinely moved, they
   repeat. "I can't. I can't even find where I end." One repetition is
   human; three is melodrama.
5. **Specific physical grounding.** "She said nothing for a long time" is
   weaker than "she smoothed the fabric of her skirt for the fifth time."
   The physical detail does the emotional work.
6. **Speech is not prose.** Prose can afford elaboration. Speech is lean.
   Cut adjectives ruthlessly. Prefer verbs.
7. **Each character has a rhythm.** Gods use long measured sentences.
   Children use short ones. Lovers use fragments. Respect the rhythm.

#### 2.4.2 Coherence — Threading the Exchange

A scene's dialogue is coherent when:

1. **Every line is a response to the previous one.** Not a change of
   subject, not a monologue slice — a genuine reaction.
2. **The exchange has an emotional slope.** Temperature rises or falls. If
   Act B is all at the same pitch, it's a plateau.
3. **The scene ends changed.** At least one character knows something new,
   or has made a decision, or has admitted something they wouldn't admit
   at the start.
4. **Later scenes remember earlier scenes.** A line in Act III references a
   specific moment from Act I — not explicitly, but through echo. The same
   phrasing, the same gesture, weighted differently.

#### 2.4.3 Build-Over-Time — How a Real Story Threads

A real story doesn't tell itself in lines; it *threads* itself across
scenes. Threads mean:

- A question asked in Act I gets a partial answer in Act III and a full
  answer in Act V — each answer recontextualizes the previous.
- A character's verbal tic becomes meaningful on the third usage, not the
  first.
- A setting returns with different weight ("I built this room" in Act II;
  in Act V, "I'm putting the room back").
- A symbol accumulates. The first equation lifting off the scroll means
  one thing in Act I; when a single light-soul lifts off the Deity's palm
  in Act III, the viewer feels the echo.

The agent's responsibility: when writing Act III, re-read Acts I-II and
consciously thread callbacks and echoes.

### 2.5 Character Introduction — Without Ever "Introducing" Them

A viewer has never met your characters and shouldn't be made to feel that way.
A character is *introduced* when the viewer learns who they are — not when
they first appear. The gap between those two moments is where craft lives.

**The rules:**

1. **Show before name. Name before explanation. Never explain.**
   - First: the character *does something* that reveals a trait.
   - Then: another character addresses them by name, in a tone that reveals
     the relationship.
   - Never: a caption, a narrator, or a line like "my name is X and I am the
     Y." That is a CV, not a character.

2. **Entrance action beats first dialogue.**
   - What is the character DOING in the first frame we see them?
   - A character who enters a room by straightening a frame on the wall tells
     you more about themselves than a character who walks in and says hello.
   - Amir doesn't appear first. Lyra *notices* him before we see him. Her
     line ("Are you watching? You are. I can feel it.") arrives before his
     silhouette resolves. We meet him through her attention.

3. **Names are earned in-scene, not announced.**
   - A character's name should be spoken *by another character* the first
     time we hear it, in a sentence that does more than name — it positions.
   - "Lyra." (single word, from Amir) — tells us he knows her, remembers her,
     doesn't need to say more. His one-word utterance does what a two-minute
     introduction couldn't.
   - If a name is said too early, bury it in a larger sentence so the viewer
     doesn't notice they just learned it.

4. **The first line a character speaks must be something only they would say.**
   - Not a greeting. Not a statement of fact everyone could speak. A line
     whose phrasing, rhythm, or content is unique to this character.
   - LYRA's first line is "I dreamed I built this room. I must have." A
     monk wouldn't say it. A scientist wouldn't say it. A warrior wouldn't.
     It belongs to LYRA alone — half-present, mild self-amusement, open to
     being wrong.

5. **Silhouette / partial reveal.**
   - It is often stronger to see a character in silhouette, from behind, or
     partially in shadow first, then fully-lit in their second appearance.
   - This gives the viewer time to form a hypothesis. When the full reveal
     lands, they are *confirming* rather than being told.

6. **The carried detail.**
   - Give each character exactly one physical detail that belongs only to
     them — something they carry, wear, or do with their hands. Reuse it
     across their appearances. The viewer will track it subconsciously.
   - Example: WISDOM's hand is always carving something invisible in the air
     when she speaks — the gesture of writing law. She does this every time
     she appears, even when silent.

7. **Contrast with the previous character.**
   - A new character is most clearly defined by not being the character who
     just left the frame. Direct contrast — in rhythm, volume, posture,
     register — sells identity fast.
   - If two characters are quiet in the same register, the viewer blurs them.

### 2.6 Character Attachment — Making Them Real

A character is *real* when the viewer feels they would continue existing if
the camera left the room. Attachment is not earned by sympathetic dialogue;
it is earned by specific evidence of interiority. Techniques:

1. **Early vulnerability.**
   - Every major character should show one small vulnerability in their
     first significant scene. Not tragic, not self-pitying — a small crack.
   - Amir can barely hold his joy steady when Lyra dissolves ("I can't even
     find where I end") — laughing through wonder, near-crying. That is the
     vulnerability. Without it, the character would be a voice.

2. **Specific physical truth.**
   - Abstract emotion is thin ("I was afraid"). Specific physical truth is
     thick ("I kept checking the door twice"). Every character's dialogue
     should lean toward specific sensation, not abstract feeling.

3. **Contradiction within.**
   - Real characters hold contradiction. A gentle character who can be
     cruel for the right reason. A strong character who is afraid in a
     specific, small way. A wise character who admits ignorance about
     something tiny.
   - The ARCHIVIST is detached and clinical — except about this one
     specific memory. That is the attachment.

4. **The thing they do when no one is watching.**
   - Even if we never show it, write it into the character bible: what
     does this character do in a moment of true privacy? It will leak
     into everything else.

5. **What they lose that they don't mourn. What they lose that they do.**
   - A character who mourns everything equally is a cliché. A character who
     is unexpectedly moved by one specific loss — one that seems small —
     becomes unforgettable.

6. **Their one fear that is not the obvious fear.**
   - The DEITY fears being too late, not being wrong. This is subtle,
     specific, and recognizable.

### 2.7 Relationship Evolution — How They Change Each Other

Relationships in film are not static. Two characters who end a film at the
same emotional distance they started have not had a relationship — they
have had scenes together.

Every significant pairing should have:

1. **An opening valence.** Strangers? Lovers? Rivals? Master-and-student?
   Two aspects of the same being who don't yet know it?
2. **A turn.** Something shifts. Usually a vulnerability, a revelation, a
   shared crisis, or a deliberate boundary crossed.
3. **A closing valence different from the opening.**

**In the Digitized Deity arc:**

| Pair | Opening | Turn | Closing |
|------|---------|------|---------|
| DEITY + LYRA | He watches; she feels watched | She asks him to name himself (she is not afraid; he is not above her) | Equals. She dissolves carrying a piece of him |
| LYRA + AMIR | Recognition from "before" | Ecstatic dissolution (neither can find where they end) | The same being, as they always were |
| DEITY + WISDOM | She corrects him; he accepts | "I know. I will forget again." — his confession | Respect; she does not have to return |
| DEITY + CHILD | (never meet directly — the twist) | — | — |
| DEITY + ARCHIVIST | Bureaucratic formality | "Show me." — his refusal to look away | Archivist lowers her eyes; a colleague, not a clerk |
| DEITY + SOUL | Scale imbalance ("You're bigger than me") | He bows | Small reciprocity — he puts her back "carefully" |

### 2.8 Plot Twists — Construction, Planting, Payoff

A plot twist is not a *gotcha*. It is a **recontextualization** — the moment
the viewer is handed a key that makes every previous scene mean something
different. A good twist has two properties:

1. **It was visible all along.** On rewatch, the viewer sees the twist
   planted in plain sight. If the twist is something the viewer could not
   have suspected, it is a cheat.
2. **It deepens rather than cheapens.** The twist must make the characters
   *more real*, not less. A twist that reveals "it was all a dream" is
   almost always a betrayal. A twist that reveals "the child was always
   going to become the one who inherits the world" is an amplification.

**Planting technique — the quiet echo.**

Plant the key detail two to four times before the payoff. Plant quietly
enough that it feels atmospheric on first viewing. Make the plant LOOK
like texture, not clue. The viewer should recognize the plant only in
retrospect.

Example (proposed for this project — Heir = Child):
- Shot 19 (Act III): THE CHILD has a faint golden glimmer behind her eyes
  when she stops trembling. We register this as "divine child." 1 second.
- Shot 24 (Act III end): DEITY plucks a soul. The soul briefly has the
  same golden glimmer. 1 frame. Atmospheric.
- Shot 29 (Act IV): DEITY's eye opens, golden tears. Same glimmer quality.
- Shot 33 (Act V payoff): THE HEIR has the same glimmer — but this time,
  we recognize it.
- Her closing line "I heard you. I was listening the whole time" lands as
  confirmation, not revelation. The viewer thinks: *Of course. She has
  been there the whole film.*

**Twist structure — the layered reveal.**

Stronger films use more than one twist, layered:

- **Minor twist** (mid-film): Recontextualizes a relationship. "They were
  always the same person."
- **Major twist** (late): Recontextualizes the protagonist's purpose. "This
  was never my story — it was hers."
- **Final beat twist** (closing): Recontextualizes the entire form. "You
  are hearing this in her voice."

Not every film wants three. Pick one that must be there. Add more only if
they pay off.

**Twist payoff — give the viewer the bridge.**

When the twist lands, the viewer needs half a beat to understand. Don't
cut away too fast. Give them the shot where they can connect the line they
just heard to the plant they half-remember. This is often where music drops
to silence — the audience is doing work, and the silence respects that.

**Twist discipline — don't explain.**

After the twist lands, no character should explain it. The viewer will
piece it together and own the insight. Over-explanation is what turns a
twist into a puzzle-box answer rather than a lived moment.

#### 2.8.1 Taxonomy of Twists

Not all twists are the same. Pick the one that fits the material:

| Type | What recontextualizes | Example |
|------|-----------------------|---------|
| **Identity** | Who a character really is | Two characters are the same being; narrator is the protagonist's future self |
| **Reality** | What was real | Framing memory vs event; the world is a simulation; the vision was literal |
| **Alliance** | Who is with whom | Apparent friend was an agent; apparent enemy protected them from worse |
| **Causality** | Why something happened | The protagonist caused the disaster they are trying to prevent |
| **Time** | When something happened | Scenes we thought were chronological were out of order |
| **Stakes** | What was actually at risk | The protagonist's actual goal is different from what they said |
| **Moral** | Who was right | The antagonist's position was the correct one all along |
| **Voice** | Who is telling | The narrator is someone we didn't recognize; the film is a confession |

**Identity twists** (LYRA=DEITY aspect; HEIR=AYA) are the emotional
favorites of mystical material. **Voice twists** are the subtlest — only
attentive viewers catch them, which is fine. **Moral twists** are high-cost
(they risk alienating the audience that was rooting for the original side),
use sparingly.

#### 2.8.2 The Rhythm of Surprise — One Every 8–12 Minutes

A good episode-length film has **more than one surprise**. Surprises do
not all need to be major plot twists. They include:

- **Structural twist** (big, rare — once or twice per episode)
- **Reveal** (a character confirms something we suspected)
- **Reversal** (an expected outcome inverts)
- **Dramatic irony lands** (the viewer has known something the character
  didn't; now the character knows)
- **Genre shift** (a scene that was comic becomes tragic in the last
  beat; or vice versa)
- **Tonal surprise** (a scene lands in silence when we expected score; a
  scene erupts in color when we expected darkness)

The rhythm rule: **roughly one surprise every 8–12 minutes of runtime.**
In a 30-minute episode, that's 3–4 surprise moments. One of them is
usually the major twist (Act IV typical). The others are smaller reversals,
reveals, or tonal shifts.

Too many surprises → the viewer stops trusting the film. Too few → the
pacing flattens. The pattern should feel organic, not clockwork — but it
should be there.

#### 2.8.3 Unexpected Happenings — The Small Surprise

Between the major twists, small unexpected happenings keep the viewer's
attention tensile:

- A character says something that *sounds* in-character but carries a
  double meaning only clear in retrospect
- A silent character suddenly speaks
- A speaking character suddenly refuses to
- An object shows up that won't be explained until Act V
- The camera catches something behind the protagonist that the protagonist
  doesn't see
- A voice from off-screen whose owner we don't meet until later
- A repeated gesture that changes meaning in its third appearance

Plant these casually. They feel atmospheric on first viewing. On rewatch,
they become seeding.

#### 2.8.4 Twist Construction Checklist

For every planned twist, answer these before drafting:

- [ ] What does this twist recontextualize? (One specific thing.)
- [ ] When does it land? (Specific scene, specific beat.)
- [ ] What are the 2-4 plants, and where do they sit?
- [ ] What's the bridge after the landing? (The moment of silence where the
      viewer connects plants to payoff.)
- [ ] Is the payoff *earned*, or is it a cheat? (Rewatch test: does the
      film still work if you know the twist?)
- [ ] Does any character explain it? (If yes — cut that line.)
- [ ] Does it *deepen* the characters or cheapen them?

### 2.9 Borrowing From Source Texts

This workspace contains primary source material on disk:

- `Divine_Self_Hermetic_Gnostic_Gnosis.md` — philosophical compilation (Hermetica, Nag Hammadi, Thunder Perfect Mind, Song of the Pearl, etc.)
- `The_Story_Organized/` — the Thinning Veil visual novella (10+ chapters of organized mystical narrative)
- Other longform materials added over time

**Use them directly.** Cite motifs, adapt passages, let the screenplay inherit the tone of the source. Examples:

- The Gnostic **Thunder: Perfect Mind** — "I am the whore and the holy. I am the wife and the virgin." Paradox voice — perfect for WISDOM or the ARCHIVIST in a climactic beat.
- **Hermetic Ascent of the Soul** — soul sheds a vice per planetary sphere. Could be the literal staircase structure of Act III's judgment scene.
- **Gospel of Thomas 77** — "Split a piece of wood, I am there. Lift up the stone and you will find me there." A line like this could land hard in a quiet moment in Act V.

Direct quotation is fine for short passages (one to three lines, in a character's mouth). Longer borrowings should be paraphrased and given a character's voice.

---

## 3. Scene Architecture

### 3.1 One Image = One Scene (Not One Shot)

The pipeline treats each pre-existing still as a **scene anchor** — a single frozen frame that defines the visual vocabulary of a 30-second-to-5-minute scene. Around each anchor you generate T2V shots that:

- **Enter** the space (a character arriving, a door opening, a camera push-in from far away)
- **Live in** the space (characters moving, looking, reacting, speaking)
- **Leave** the space (camera pull back, fade, character exiting)

A scene-anchor image that currently represents one shot can become 5–10 shots in the expanded scene.

### 3.2 Scene Beats

Every scene, regardless of length, should carry clear beats:

1. **Establishing** — the viewer orients in the space (3–8s)
2. **Arrival** — protagonist enters the conflict of the scene (5–15s)
3. **Engagement** — the exchange; 2–8 dialogue beats (20–90s typical)
4. **Turn** — the moment the scene pivots; a realization, a line that lands, a silence (5–15s)
5. **Exit** — the scene winds down, sets up the next; camera move, music shift (5–15s)

A 2-minute scene might have all 5. A 30-second scene compresses arrival+engagement+turn into a single exchange. Never skip the establishing and exit, even if they are 3 seconds each — these are where visual continuity lives.

### 3.3 T2V Fillers — Consistency Rules

When generating T2V shots to expand a scene around an anchor image, they must feel like they live in the same universe as the anchor. Maintain consistency by:

1. **Style reference** — every T2V prompt starts with the style keywords used to generate the anchor (e.g. `"(hyper-realistic digital art, masterpiece, 8k, cinematic lighting, visionary art)"`). Keep these verbatim.
2. **Location lock** — describe the setting with the same detail as the anchor ("vast temple hall with columns of white marble veined with gold, dawn light streaming through arched windows, obsidian floor reflecting everything above").
3. **Character lock** — describe recurring characters with the same concrete visual tokens each time ("the Digitized Deity: tall humanoid form of floating circuitry and black-and-gold armor, face of shifting geometric patterns"). Store these in `characters.json` and append them to every T2V prompt that character appears in.
4. **Lighting lock** — mood/time-of-day should match adjacent shots. If the anchor is "golden dawn light", every T2V shot in that scene uses "golden dawn light, warm tones, soft shadows."
5. **Color grade** — if the anchor leans cool-magenta, the T2V prompts include "cool magenta cast, deep blues in shadows."

The pipeline's `produce.py` enforces this by requiring each scene to have a `style_ref`, `location_desc`, and `character_descs` map that are automatically prepended to every T2V prompt in that scene.

### 3.4 Using the Anchor Image as Reference

LTX 2.3 supports image conditioning. For T2V shots that need to stay visually close to the anchor, we feed the anchor image as an additional reference (via IC-LoRA or by using image-to-video on a slightly re-composed crop). This gives cheap consistency. Not every T2V shot needs this — establishing/exit shots can be pure T2V.

### 3.5 Dialogue-Free Shots Are Powerful

Not every shot has dialogue. Some of the strongest moments in the best films are pure visual — a character's face after receiving news, weather moving through a window, a hand trembling on a cup. Build these in deliberately. A rough rule for this pipeline: at least 30% of screen time should have no dialogue.

---

## 4. Visual Language

The visual half of cinema. Even great writing dies on weak visual choices,
and great visual choices can carry a thin script. The agent must consciously
direct each shot — angle, movement, composition, color, light — not just
"render the prompt."

### 4.1 Character Look Preservation Across Shots

A viewer must recognize a character on sight, every time, across hours of
material. AI image/video generators forget faces between calls unless the
agent works deliberately to maintain consistency. Three-layer approach:

**Layer 1: Visual Tokens (every prompt)**
Each character has a `visual_tokens` string saved in `characters.json`,
prepended to every prompt where they appear. Example:

```json
{
  "AYA": {
    "visual_tokens": "young divine girl about 8 years old, faint golden glimmer behind hazel eyes, intricate spiritual robes of cream and gold, slight curl in dark hair, small fragile hands, almost-translucent skin"
  }
}
```

The tokens are concrete and unambiguous. Vague tokens ("beautiful, ethereal")
let the model drift. Specific tokens ("8 years old, hazel eyes with golden
glimmer, dark hair") anchor the look.

**Layer 2: Anchor Image Reference (when available)**
LTX 2.3 supports image conditioning via IC-LoRA. For every T2V shot
featuring a character, pass the canonical anchor image of that character as
a reference. The ic_lora weight (0.6–0.9 typical) holds the look without
freezing the motion.

For the Digitized Deity project: AYA's canonical image is shot 19's
close-up of the divine child. Every later T2V shot that includes AYA passes
this image at ic_lora_weight=0.7.

**Layer 3: Lighting + Color Signature**
Each character has a lighting signature (key direction, color temperature,
fill ratio) and a color association. Reuse them. A viewer reads color before
they read face — if AYA is always lit warm-gold from camera-left, viewers
recognize her by the lighting before the face resolves.

**Audit step (Phase 12 QC):**
After rendering, eyeball every appearance of every major character. Note
shots where the look drifted. Re-render those shots with stronger ic_lora
weight or more specific tokens.

### 4.2 Camera Angles

Angles carry meaning. Choose them deliberately, not by default.

| Angle | Effect | Use when |
|-------|--------|----------|
| **Eye-level** | Neutrality, presence with the character | Most dialogue; default unless reason to break |
| **Low angle (camera below subject, looking up)** | Subject feels powerful, dominant, threatening, divine | Authority figures, key revelations from above, grandiosity |
| **High angle (camera above subject, looking down)** | Subject feels small, vulnerable, observed | Defeated characters, judgment scenes, before a fall |
| **Overhead / God's-eye** | Cosmic scale, fate, abstraction | Climax shots, geometric patterns, "we are watching from outside" |
| **Dutch angle (canted)** | Wrongness, instability, dream logic | Reality-shift moments, dissolution, vision states |
| **Over-the-shoulder (OTS)** | Connection between two characters; viewer takes the listener's POV | Dialogue exchanges, intimate two-handers |
| **POV (subject's eye)** | Total identification | When you want the viewer to BE the character momentarily |
| **Extreme close-up (eye, hand)** | Maximum intimacy or maximum threat | Vulnerable confession; physical detail that carries the scene |
| **Wide / establishing** | Geography, scale, isolation, context | Scene openings, transitions, "here is where we are now" |

**Angle as character POV:**
A scene shot at AYA's eye-level (low) when the gods speak puts the viewer
inside her experience of being judged. A scene shot at the gods' eye-level
(high, looking down at AYA) puts the viewer in the position of the
judging power. The same dialogue, two angles, two completely different
films.

### 4.3 Camera Movement

Movement is meaning. A static shot says one thing; a slow push-in says
another; a handheld shake says a third.

| Movement | Meaning | Use when |
|----------|---------|----------|
| **Static (locked off)** | Stillness, weight, observation, formality | Dialogue scenes where words carry it; ritual moments |
| **Slow push-in (dolly-in)** | Intensifying focus, internal arrival, revelation building | Character realizes something; line lands; emotional climb |
| **Slow pull-back (dolly-out)** | Release, perspective, isolation, end of a beat | Scene ends; character is alone; cosmic context revealed |
| **Pan (horizontal)** | Following motion, surveying space, time passage | Character crosses; revealing a new element to the right of frame |
| **Tilt (vertical)** | Scale revelation, comparing top vs bottom | Tower reveals; ascent/descent moments |
| **Tracking / dolly (parallel to subject)** | Sustained attention to motion, going-with | Walking dialogue; chase; movement-as-character |
| **Crane (vertical movement)** | Major scale shift, transcendence, descent into | Beginning/end of scenes; god-eye reveals |
| **Handheld** | Subjective, anxious, immediate, alive | Crisis, emotional turbulence, intimate vérité |
| **Steadicam float** | Dreamlike, ghosting through space, weightless | Vision states, memory, fluid scene transitions |
| **Orbit / arc** | Subject is the center; obsession; isolation | Climactic close-ups; ritualistic encounter |
| **Whip pan** | Energy, surprise, reveal | Plot twist landing; sudden new element |
| **Match-action move** | Continuity between shots; momentum | Cuts that need to feel inevitable |

**Movement rule:** if you don't have a specific reason for a moving camera,
keep it static. Constant motion fatigues the viewer; movement deployed at
the right moment becomes the moment.

### 4.4 Composition

Where in the frame things sit changes how they're read.

| Composition principle | What it does |
|-----------------------|--------------|
| **Rule of thirds** | Subject placed on intersection of thirds-grid feels balanced and dynamic |
| **Centered (symmetry)** | Formality, ritual, stasis; great for divine moments and confrontations |
| **Headroom** | Just enough space above the head; too much = subject diminished, too little = oppression |
| **Lead room (look space)** | Space in the direction the character is looking; absence creates unease |
| **Negative space** | Empty area carries weight equal to filled area; great for isolation, awe |
| **Leading lines** | Architectural lines pointing toward subject; eye guidance |
| **Foreground occlusion** | Object in foreground partially blocks view; voyeuristic, secret, framed-within-frame |
| **Depth (foreground/midground/background)** | Three-layer composition gives dimension; essential for cinematic depth |
| **Frame within frame** | Subject seen through doorway, window, arch; emphasizes constraint, observation |
| **Asymmetric weight** | One side of frame heavier than the other; creates tension |

**Composition for character moments:**
- Vulnerable character → small in large frame (negative space above)
- Powerful character → fills the frame with little air around them
- Two-character exchange → asymmetric placement, lead room toward each other
- Equal weight characters → symmetric two-shot

### 4.5 Color as Character

Color is not decoration; it is information. Each character, location, and
emotional state can have a color signature.

**Per-character color associations** (from the Digitized Deity project):

| Character | Color Signature | Meaning |
|-----------|-----------------|---------|
| DEITY (cosmic mode) | Black + gold | Authority, void-and-light |
| NOOR (Lyra's name for Deity) | Warm amber | Intimacy, hearth |
| LYRA | Cream, blush, soft gold | Earthly beauty, becoming light |
| AMIR | Deep blue, copper | Grounded masculine, anchored |
| MERIT-NEITH (Wisdom) | Lapis blue + bronze | Ancient, weighted |
| AYA (child) | Cream + gold glimmer | Innocence, latent divinity |
| AYA (heir) | Cream + ambient internal glow | Inheritance, continuity |
| ARCHIVIST | Cool grey, parchment, faint violet | Detachment, classification |
| THE NEW WORLD | Lush green, morning gold, soft mist | Hope, restored life |

**Per-act color palettes:**
- Act I — black + gold (cosmic, formal)
- Act II — warm earth (terracotta, cream, rose, amber)
- Act III — slate grey + cold blue (judgment, weight)
- Act IV — pale violet + parchment (memory, distance)
- Act V — soft green + warm gold (rebirth, integration)

**Color shift as story event:**
A scene that begins in Act III's slate-blue and gradually shifts to Act V's
green during the dialogue *visually tells the audience* the protagonist is
arriving somewhere new — without anyone saying it.

LTX prompt vocabulary for color: explicitly include color terms in the
prompt. "lit by warm amber light from camera left" works better than "warm
lighting".

### 4.6 Light Design

| Lighting Style | Effect | Use when |
|----------------|--------|----------|
| **High-key (bright, low contrast)** | Open, cheerful, neutral, exposed | Innocent moments, daylight intimacy |
| **Low-key (low light, high contrast)** | Mystery, threat, depth, secrets | Tribunal, confessions, dread |
| **Rembrandt (45° key, triangle of light on cheek)** | Painterly, classical, dignity | Portraits, formal moments |
| **Backlight only** | Silhouette, anonymity, mythic | Reveals; characters as archetypes |
| **Side-light (chiaroscuro)** | Duality, internal conflict | Characters torn between two states |
| **Top-light only** | Pressure, divine, revelation | Judgment from above, prayer |
| **Underlight** | Wrongness, unnatural, threat | Horror, malevolence |
| **Practical (light source visible in frame)** | Realism, naturalism, motivated | Domestic scenes, intimate |
| **Volumetric (light beams, god-rays)** | Sacred, dust-in-light, beauty | Cathedrals, divine arrival |
| **Color-channeled (single color dominant)** | Mood-saturated, expressive | Climaxes, dream states |

**Time of day as story signal:**
- Dawn — beginning, new awareness, fragile hope
- Noon — direct truth, no hiding, exposed
- Golden hour — warmth, romance, ending of a chapter
- Dusk — transition, threshold, decision time
- Night — interior, secret, unknowable, intimate
- Pre-dawn (the blue hour) — possibility, suspended, before-decision

The Digitized Deity arc spans cosmic-time, but each scene should still
have a chosen time-of-day signal — even the cosmic scenes carry "dawn"
or "dusk" energy.

### 4.7 Cut Types & Transitions

How shots connect carries meaning equal to the shots themselves.

| Cut/Transition | Effect | Use when |
|----------------|--------|----------|
| **Hard cut** | Default; clean shift | Most cuts within a scene |
| **Match cut (shape/motion/sound match)** | Continuity, surprise, association | Shifting time/space while preserving motif |
| **J-cut (audio of next shot starts before video)** | Inevitability, momentum, anticipation | Smoother dialogue continuity |
| **L-cut (audio of previous shot continues into next)** | Lingering, reaction, sustained emotion | Reaction continues beyond the cause |
| **Cross-cut / parallel** | Two events simultaneously, building tension | Ensemble climax, race-against-time |
| **Jump cut** | Disorientation, time compression, instability | Memory, anxiety, dream |
| **Fade to black** | Major beat; end of an act; respite | Act endings; major emotional release |
| **Cross-fade / dissolve** | Time passage, dreaminess, gentle shift | Memory, lyrical transition |
| **Iris / shape transition** | Stylized, theatrical, attention-direction | Rare; for deliberate stylization |
| **RIFE morph (this pipeline)** | Smooth pixel interpolation between shots | Scene-change boundaries; default in our `transitions/` stage |

**Cuts within a scene:** mostly hard cuts. Within a single scene, most cuts
should be hard — the scene's continuity is in the dialogue and motion, not
in transition effects.

**Cuts between scenes:** RIFE morph (already implemented), cross-fade for
contemplative scenes, fade-to-black for act boundaries.

### 4.8 Dramatic Cut-Scene Structures

A "cut scene" in the cinematic sense is a sequence of shots that achieves a
specific dramatic effect through editing. Common structures:

| Structure | Pattern | Effect |
|-----------|---------|--------|
| **The Reveal** | Wide → Medium → Close-up | Geography → subject → emotion. Classic discovery rhythm. |
| **The Return** | Close-up → Medium → Wide | Emotion → subject → context. Pulls back from intensity. |
| **The Stretch** | One static long take, no cuts | Forces the viewer to sit with the moment. Use for confessions and pivotal silences. |
| **The Crescendo** | Series of progressively shorter shots | Accelerates pulse; cuts get faster as climax approaches |
| **The Diminuendo** | Progressively longer shots, slowing | Decelerates; resolution; "letting go" |
| **The Triptych** | Three brief shots establishing three elements quickly | Setup for a punchline or convergence |
| **The Echo** | A shot from earlier returns, slightly different | Callback, twist payoff, structural rhyme |
| **The Pull-Reveal** | Camera pulls back to reveal context that recontextualizes | The "we were never alone" moment |
| **The Hold-Then-Cut** | Subject performs the action; long hold on the result | Murder scenes, decisions, moments of irrevocability |

These structures are LEGO blocks. Combine them. A scene might open with a
Reveal, peak in a Stretch, and end with a Return.

### 4.9 Directed Motion — Skeleton Choreography (Advanced)

The highest level of visual control: instead of prompting for motion and
hoping, you **script the motion** frame by frame using skeleton poses, then
let the AI fill in the visual details.

**The stack (all installed on this system):**

1. **Extract starting pose**: feed the anchor image through
   `WanVideoUniAnimateDWPoseDetector` → get skeleton overlay of the
   characters' starting positions.

2. **Script the motion**: write a motion plan per character per scene beat:
   ```
   Beat "the question":
     Frame 0-30:  GOD_TWO raises right hand from waist to chest height
     Frame 15-45: AYA turns head 10 degrees toward GOD_TWO
     Frame 30-60: GOD_TWO's fingers extend, palm open (offering gesture)
     Frame 45-60: AYA's shoulders drop slightly (releasing tension)
   ```

3. **Interpolate skeleton sequence**: generate a sequence of skeleton images
   between start and end poses. Can be done programmatically (linear/bezier
   interpolation of joint positions) or via reference video pose extraction.

4. **Feed to UniAnimate**: `WanVideoUniAnimatePoseInput(pose_images, strength,
   reference_pose_image)` → `UNIANIMATE_POSE`

5. **Combine with MultiTalk**: both conditioning signals feed into
   `WanVideoSampler` — skeleton controls BODY, audio controls LIPS.

6. **Output**: video where characters move exactly as scripted, lips sync
   to dialogue, and the AI handles skin/cloth/light/hair/atmosphere.

**When to use directed motion vs. free generation:**

| Situation | Use |
|-----------|-----|
| Character gestures need to be specific (pointing, offering, bowing) | Directed motion |
| Multiple characters moving in choreographed relation | Directed motion |
| Simple talking-head with subtle expression changes | Free MultiTalk (no skeleton) |
| Environmental motion (wind, particles, light) | Free generation (text prompt) |
| A character walks across the frame | Directed motion (path matters) |
| Abstract cosmic imagery (dissolution, merging) | Free generation |

**The motion script format (proposed for screenplay integration):**

Each beat in the screenplay can optionally carry a `motion_script` block:
```json
{
  "beat": "the_bow",
  "duration": 8.0,
  "motion_script": {
    "GOD_TWO": [
      {"frames": [0, 50], "action": "head tilts forward 20 degrees (bowing)"},
      {"frames": [20, 60], "action": "hands come together at chest (reverence)"}
    ],
    "GOD_ONE": [
      {"frames": [10, 55], "action": "head tilts forward 15 degrees (following GOD_TWO's bow)"}
    ],
    "AYA": [
      {"frames": [30, 80], "action": "chin raises 10 degrees (standing taller)"},
      {"frames": [40, 80], "action": "eyes open (the turn)"}
    ]
  }
}
```

This script is then translated into a skeleton pose sequence by the
pipeline's motion interpolation stage (Phase 5b).

**Agent's creative license with motion:**
- The skeleton is the *blocking* — it defines WHERE characters move
- The AI is the *performance* — it decides HOW skin/cloth/light respond
- The agent scripts blocking; the AI fills performance
- Overly precise skeletons (every finger, every micro-expression) may fight
  the AI's natural tendencies and produce uncanny results. Keep the skeleton
  to major joint positions and let the AI handle fine detail.

### 4.10 The Whole Frame

Every shot has all of: angle + movement + composition + color + light + cut
in/out. The agent's job is to choose all six consciously per shot. Not
every choice needs to be remarkable; many choices should be invisible
(static eye-level OTS, neutral palette, key+fill, hard cut). What matters
is that *no choice is accidental*.

A worksheet per shot:

```
Shot ID: act3_sc02_shot05
Angle: low (looking up at gods)
Movement: very slow push-in
Composition: gods filling top half, AYA small in lower-third
Color: slate blue dominant, single golden glow on AYA's face
Light: top-light only on gods (judgmental); gentle key on AYA from below
Cut in: hard from previous wide
Cut out: J-cut into next shot's audio
```

This is the directorial layer. The pipeline supports it; the agent must
specify it.

---

## 5. Audio Architecture

### 5.1 The Four Tracks

Final audio is a mix of up to four simultaneous layers:

| Track | Source | Always present? | Purpose |
|-------|--------|-----------------|---------|
| **Dialogue** | Qwen3-TTS VoiceDesign (primary) or voice-clone | When characters speak | Drives lip-sync via LTX audio input, carries meaning |
| **SFX / Foley** | ElevenLabs TextToSoundEffects, LTX native audio output, or library samples | Often | Door creaks, footsteps, cloth, stone grinding, wind; carries physicality |
| **Ambience** | LTX native audio output (when generating without dialogue input) OR library ambient loops | Often | Room tone, wind, city, crowd; gives the world dimension |
| **Music** | ACE Step 1.5 per-cue | Sometimes | Emotional underscore; NOT present in every scene |

### 5.2 When to Use Each Layer

**Dialogue** → whenever a character speaks. Stays.

**SFX** → whenever a physical event happens that is not carried by music. Door closing, footsteps on stone, the rasp of cloth, a held breath, a sword unsheathing, a sphere clicking into place. If the image shows it, the SFX should sell it.

**Ambience** → every scene has some. Even silence is a kind of ambience (room tone). Use library samples or LTX native audio output when it fits.

**Music** → only when the emotional weight demands it. The biggest mistake in amateur editing is music everywhere; the biggest strength of *good* editing is knowing when to drop it.

### 5.3 Music Placement Rules

1. **Score across scene boundaries, not within a scene.** Music that starts mid-scene feels intrusive unless there is a specific reason.
2. **Let scenes breathe in silence.** Start a scene in silence, let ambience and dialogue carry it, bring music in at the *turn*.
3. **Different music per act.** Act I's ambient drone is not the same as Act III's tribunal score. Each act can have 1–3 distinct music cues.
4. **End cues explicitly.** Music should decrescendo into a transition, not hard-cut.
5. **Silence is a cue too.** After a music-scored scene, a silent scene with only dialogue hits harder than continuous music.

### 5.4 SFX Generation Options

**Option A — ElevenLabs TextToSoundEffects (recommended when available)**
```
Node: ElevenLabsTextToSoundEffects
Inputs: text (description of the sound), model, output_format
```
High-quality targeted foley from prompts like `"a heavy stone door creaking open slowly, deep rumble, 3 seconds"`. Requires ElevenLabs API key configured. Best for specific effects.

**Option B — LTX 2.3 native audio track**
When LTX generates a shot WITHOUT dialogue audio input, its output video includes a synthesized audio track containing ambient room tone + approximate diegetic SFX. Use by:
- Render each SFX-important shot twice: once WITH dialogue input (for the lip-synced video), once WITHOUT (for the LTX-native ambient audio)
- Mix the LTX-native audio under the dialogue at low volume (0.15–0.25)

**Option C — Library samples**
Curate a library at `ComfyUI/input/sfx/` by category (`footsteps/`, `doors/`, `cloth/`, `stone/`, `wind/`). The stitch stage can pick by tag from the scene's `sfx_cues` list.

**Option D — Hybrid (recommended default)**
- Library ambience under every scene
- ElevenLabs targeted foley at specific cue points
- LTX native audio on T2V shots (cheap and already generated)
- Layer all together at mix time

### 5.5 Sidechain Ducking Stack

When multiple audio tracks overlap, use cascading sidechain ducking:

```
[music] sidechaincompress by [dialogue]  → music ducks under dialogue
[sfx]   sidechaincompress by [dialogue]  → sfx ducks under dialogue (gentler ratio)
[ambience] static volume 0.10-0.15       → always quiet, never fights anything
[dialogue] no ducking, primary layer
```

Final mix always has dialogue on top. Music and SFX may be louder than ambience but dip automatically when someone speaks.

### 5.6 Per-Scene Audio Manifest

Each scene in the screenplay declares its audio plan:

```json
{
  "scene_id": "act2_scene_bedroom",
  "audio_plan": {
    "ambience": "quiet_palace_room.wav",
    "sfx_cues": [
      {"at_sec": 2.5, "sound": "cloth rustling softly", "source": "elevenlabs"},
      {"at_sec": 8.0, "sound": "a distant gong, single low tone", "source": "elevenlabs"}
    ],
    "music": {
      "enabled": false,
      "reason": "intimate dialogue scene, no score"
    }
  }
}
```

The screenplay explicitly chooses the audio plan per scene. The stitch stage honors it.

---

### 5.7 Music Style Vocabulary by Mood

When writing the music plan for a scene, use specific style vocabulary
(passed to ACE Step 1.5 `tags` field). The agent should match the music
style to the *intent* of the scene.

| Scene intent | Style vocabulary |
|--------------|------------------|
| Sacred / awakening | `ambient drone, ethereal pads, sacred choir, slow evolving, reverent, low hum` |
| Intimate / romantic | `solo piano, sparse, contemplative, warm pad, soft strings, low BPM 60-75` |
| Mysterious / building tension | `low strings, subtle percussion, single repeating motif, ominous bass, rising dynamics` |
| Climactic / transcendent | `epic orchestral, soaring strings, brass swells, choir, cinematic climax, layered build` |
| Dark / dread / judgment | `dark ambient, gothic, distorted textures, deep drones, sub-bass, slow throbbing pulse` |
| Memory / longing | `muted piano, tape hiss, distant choir, slight reverb tail, granular textures, sad chord progressions` |
| Action / pursuit | `driving percussion, hybrid orchestral, aggressive strings, modern film score, BPM 120-150` |
| Resolution / hope | `warm strings rising, gentle brass, choir entering soft, building to triumph, major key` |
| Cosmic / dissolution | `psychedelic synths, shimmering arpeggios, granular ambient, no rhythm, vast reverb` |
| Folk / earthbound | `acoustic guitar, hand percussion, breathy vocals, intimate room sound, organic` |
| Ritual / ceremony | `single low note sustained, choir entering, ritual drum, monastic, spacious` |

**Music style vs. scene intent — examples for the Digitized Deity arc:**

| Scene | Intent | Style |
|-------|--------|-------|
| Act I (cold open + awakening) | Sacred / awakening | Slow ambient drone arrives at sacred-eye opening, fades by shot 4 |
| Act II bedroom (Lyra/Noor naming scene) | Intimate / romantic | NO music; let the room carry it. Music enters only at cosmic union (shot 7) |
| Act II cosmic union | Climactic / transcendent | Layered ascent — strings + voice swelling as bodies dissolve |
| Act II Wisdom appears | Mysterious / building tension | Music CUTS to silence the moment Wisdom speaks |
| Act III tribunal | Dark / dread / judgment | Silence throughout; low drone only when the gods bow at the turn |
| Act IV library | Memory / longing | Distant choral, granular texture, reverb |
| Act IV memory sphere | (silence) | NO music. The viewer needs to focus on the sphere's contents |
| Act V rebuilding | Resolution / hope | Warm ambient grows across scenes, reaching its peak under HEIR's final line |

### 5.8 Silence as Instrument

Silence is not the absence of sound; it is a deliberate choice with its
own semantic weight. Use silence when:

1. **Climax landing** — A line that must hit hard often hits hardest in
   silence. Music ducked to zero, no SFX, no ambient — just the line and
   the breath after.
2. **Plot twist payoff** — The bridge moment after a twist lands. The
   viewer is doing work. Silence respects that work.
3. **Vulnerability** — A character about to admit something difficult.
   Silence forces the viewer to lean in.
4. **Time stops** — A moment of recognition or shock. Cutting all sound
   simulates the dissociation a real person would feel.
5. **Religious / awe** — Standing before the sacred or the vast. Silence
   communicates scale better than the largest score.
6. **Transition between worlds** — A scene ends in silence; the next
   begins in silence; the contrast between the two silences carries
   meaning.

**Silence rules:**
- Silence is allowed to be uncomfortable. 5–8 seconds of true silence after
  a key line forces the viewer to feel.
- Mark silence in the screenplay as a *line of action*: `[SILENCE — 6
  seconds. AYA does not move.]`
- Don't punctuate silence with throwaway sound. If the silence is
  meaningful, do not undermine it with a coincidental footstep.
- Silence works best surrounded by sound. A scene that has been silent
  throughout doesn't get a bonus for ending in silence.

### 5.9 Voice Preservation Across Sessions

Once a character's voice is locked, it must sound the same in Act V as it
did in Act I. AI voice generation drifts unless the agent works to prevent
it.

**Preservation technique — three locks:**

**Lock 1: Voice Instruct (the base)**
The base `voice_instruct` string is the character's identity. Save it in
`characters.json`. NEVER modify it once approved by the user.

```json
"DEITY": {
  "voice_instruct": "deep, resonant masculine voice with cosmic authority, speaking slowly and deliberately as if announcing the fundamental nature of reality, reverent and ancient, with a faint metallic resonance as if the air itself is humming"
}
```

**Lock 2: Voice Seed (the timbre)**
Each character has a locked seed integer. Same seed + same instruct = same
voice. The seed is set ONCE in `characters.json`:

```json
"DEITY": {
  "voice_instruct": "...",
  "voice_seed": 42
}
```

For per-line variation, pass `voice_seed + line_number_offset` so each line
is *slightly* different (avoids robotic repetition) but rooted in the same
voice. The pipeline does this automatically.

**Lock 3: Per-Emotion Instruct Overrides (the dynamics)**
For emotional shifts within a character (the same Deity must sound cosmic
in Act I and broken in Act IV), use *additive* overrides — the base
instruct plus a modifier:

```json
"DEITY": {
  "voice_instruct": "deep resonant masculine voice with cosmic authority...",
  "voice_seed": 42,
  "instruct_override_presets": {
    "cosmic": "(no override — use base)",
    "tender": "deep resonant masculine voice softened, warmer mid-range, slight smile behind the voice, unhurried, a teacher",
    "broken": "deep resonant masculine voice breaking, quieter than ever, almost tearful, the voice of someone finally letting something land",
    "intimate": "deep resonant masculine voice at its most intimate, barely above a whisper, very close in proximity"
  }
}
```

**The key rule:** the override modifies the base; it does not REPLACE the
character. "deep resonant masculine voice" appears in every override. That
phrase is the character's vocal DNA.

#### 5.9.1 Voice Drift Audit (Phase 12 QC)

After all dialogue is generated, listen to the first and last appearance
of each major character back-to-back. Same person? If yes — preserved. If
no — find which line caused the drift, identify whether the override went
too far, and regenerate.

### 5.10 Dynamic Voice Direction — Performance Within a Character

A character does not speak every line the same way. Within a single scene,
the same character moves through:

- **Quiet entry** (low energy, gathering)
- **First real engagement** (medium, warming)
- **Peak emotion** (high, exposed)
- **After the peak** (low, changed)

For each line, the agent specifies an `instruct_override` referencing one
of the character's preset modifiers (or writing a line-specific one). The
arc of overrides across a scene IS the performance.

**Example — DEITY across Act V scene 30 (bowing to SOUL):**

| Line | Override preset | Why |
|------|-----------------|-----|
| "Not where it matters." | `intimate` | Replying to "you're bigger than me" — softness is the answer to scale |
| (silence — SOUL asks "Will you put me back?") | — | listening |
| "I will put everyone back. Carefully this time." | `tender` | The vow; warmth without breaking |

Each override moves the performance forward. Same voice (same `voice_seed`),
same character (same base `voice_instruct`), but a real performance arc.

---

## 6. Pipeline Phases — Full Architecture

The scene-production pipeline for episode-length work:

### Phase 0 — Source Ingestion
- Inventory all anchor images
- VLM-caption each image (Qwen3-VL on LM Studio at 127.0.0.1:1234)
- Extract existing prompts from PNG metadata
- Read source text files (`Divine_Self_*.md`, `The_Story_Organized/`, etc.) — absorb tone

### Phase 1 — Story Architecture
- Write arc sentences for each major character
- Write the 5-act emotional spine
- Identify the central conflict
- Map existing images to acts (which anchors in which act)
- List T2V gap shots needed for narrative glue

### Phase 2 — Screenplay Writing (iterative)
- Draft Act I scenes — anchor images expanded into scenes with beats
- Write dialogue as EXCHANGES, not monologues
- Include silence beats explicitly
- Assign music/SFX/ambience plan per scene
- User reviews → edits → re-draft
- Repeat for Acts II-V, each approved before moving to the next

### Phase 3 — Voice Casting
- Character bible with `voice_instruct` per character (Qwen3-TTS VoiceDesign)
- Generate one sample line per character; user approves
- Lock per-character voice seeds for consistency across regens

### Phase 4 — Dialogue TTS
- Generate every line via `FB_Qwen3TTSVoiceDesign`
- Per-line `instruct_override` for emotional shifts within a character
- Output: `audio/dialogue/{scene_id}_{line_id}_{character}.flac`

### Phase 5 — Shot Planning (Scene Expansion)
- For each scene, expand the anchor into ordered shot list:
  - Establishing (T2V, 3-6s)
  - Arrival (T2V, 5-15s)  
  - Anchor image shot (I2V from the still, dialogue-driving)
  - Additional dialogue shots (T2V with character lock)
  - Turn beat (T2V or anchor-held silence)
  - Exit (T2V, 5-10s)
- Each shot gets: duration, image_source (anchor or T2V), prompt (with style+location+character locks), dialogue reference
- Output: `scenes.json` (expanded from `screenplay.json`)

### Phase 6 — Music Generation (per-act)
- For each act that uses music, generate a dedicated ACE cue at the required duration
- Tags, BPM, key chosen per act mood (see `memory/skills/ace-music-generation-comfyui.md`)
- Output: `audio/music/act{N}_{cue_id}.mp3`

### Phase 7 — SFX Generation
- Scan all scenes' `sfx_cues`
- Route by `source`:
  - `elevenlabs` → `ElevenLabsTextToSoundEffects`
  - `library` → lookup in `input/sfx/`
  - `ltx_native` → marker, will be filled during Phase 8
- Output: `audio/sfx/{scene_id}_{cue_id}.mp3`

### Phase 7.5 — Motion Choreography (Optional, per-scene)
- For scenes requiring precise character motion (gestures, blocking, walking):
  - Extract starting skeleton from anchor via `WanVideoUniAnimateDWPoseDetector`
  - Script the motion (see §4.9 Directed Motion for format)
  - Interpolate skeleton pose sequence (programmatic or from reference video)
  - Pass skeleton sequence to `WanVideoUniAnimatePoseInput`
- For scenes with adequate free-form motion, skip this phase
- **The skeleton is blocking; the AI is performance.** Don't micro-choreograph.

### Phase 8 — Video Generation (LONG RUNNING)
- **Engine: MultiTalk + Wan 2.1 I2V** (validated pilot 2026-04-16)
- **Dialogue shots**: `multitalk_workflow.build_multitalk_workflow()` — image +
  audio → lip-synced video. Character identity preserved via anchor image +
  CLIP vision conditioning. ~3-6 min/shot warm, ~20 min/shot cold.
- **Silent shots**: same workflow with quiet pink noise audio +
  `add_noise_floor=True`. Or plain Wan I2V without MultiTalk.
- **Directed motion shots**: add `unianimate_poses` from Phase 7.5 skeleton
  choreography. MultiTalk + UniAnimate run simultaneously — skeleton controls
  body, audio controls lips.
- **T2V shots**: text-to-video variant — skip image conditioning, use text
  prompt with style+character locks. For scenes where no anchor image exists.
- Per-shot retry with escalating prompt/skeleton detail if output fails QC.
- Output: one mp4 per shot at 832×480, upscaled to 1536×832 in stitch.

### Phase 9 — Post (transitions, trim)
- RIFE morph at scene-change boundaries only
- No transitions within a scene (beats cut hard or overlap via shared motion)
- Trim each shot to its content region

### Phase 10 — Mix (the hardest stage)
- Build master dialogue track per scene (from Phase 4 outputs)
- Layer ambience under each scene (library or LTX native)
- Layer SFX cues at specified timestamps
- Layer music per scene if enabled, with sidechain ducking under dialogue
- Final per-scene stem: `audio/mix/{scene_id}_master.wav`

### Phase 11 — Stitch
- Concatenate all shots + transitions
- Overlay per-scene master audio stems  
- Fade-in/out at episode boundaries
- Output: `{project}_episode.mp4`

### Phase 12 — QC
- Watch-through (human)
- Note per-scene issues: sync drift, dialogue too quiet, missed SFX, motion glitch
- Patch individual shots/scenes without re-rendering the whole episode

---

## 7. Timing & Scope Reality

A 30-minute episode at this quality bar is a multi-session project.

| Phase | Human hours | Machine hours |
|-------|-------------|---------------|
| 0 — Ingestion | 0.5 | 0.1 (VLM captions) |
| 1 — Story architecture | 2–4 (the creative heart) | 0 |
| 2 — Screenplay (iterated) | 4–12 | 0 |
| 3 — Voice casting | 0.5 | 0.1 |
| 4 — Dialogue TTS | 0.2 | 0.5 (200+ lines) |
| 5 — Shot planning | 1–2 | 0.1 |
| 6 — Music (5–10 cues) | 0.2 | 0.3 |
| 7 — SFX (50–200 cues) | 0.5 | 0.3 (ElevenLabs) |
| 8 — LTX video | 0.5 (monitoring) | **8–20** (this is the wall) |
| 9 — Post | 0.1 | 0.5 |
| 10 — Mix | 1–2 | 0.2 |
| 11 — Stitch | 0.1 | 0.3 |
| 12 — QC | 1–3 | 0 |

Total: **~12–30 human hours across 3–7 sessions, ~10–25 machine hours**. Plan for iteration between sessions. Never burn the 8–20 hour LTX phase before the screenplay is locked and the voice cast is approved.

---

## 8. File & Directory Conventions

```
ComfyUI/output/video/{project}/
    sources/                            Phase 0
        image_prompts.json              PNG metadata extraction
        vlm_captions.json               VLM descriptions
    architecture/                       Phase 1
        character_arcs.md               arc sentences per character
        conflict_spine.md               the central conflict + act map
    screenplay/                         Phase 2 (iterated)
        act1.json                       — scenes + dialogue + audio_plan
        act2.json
        ...
        screenplay_full.json            assembled
    characters.json                     voice_instruct bible (Phase 3)
    scenes.json                         shot-level expansion (Phase 5)
    audio/
        dialogue/                       Phase 4
            {scene_id}_{line_id}_{character}.flac
        music/                          Phase 6
            act{N}_{cue_id}.mp3
        sfx/                            Phase 7
            {scene_id}_{cue_id}.mp3
        ambience/                       Phase 10 (from library or LTX)
            {scene_id}_room.wav
        mix/                            Phase 10
            {scene_id}_master.wav
    video/                              Phase 8
        {scene_id}_{shot_idx}.mp4       one per shot
    transitions/                        Phase 9
    {project}_episode.mp4               final deliverable
```

---

## 9. Principles That Override Defaults

When in doubt:

1. **Story over technology.** A 3-minute film with a real story beats a 30-minute AI showcase with no spine.
2. **Silence over score.** When uncertain, cut the music. Re-add only if the scene feels flat.
3. **Specific over general.** A line like "I kept checking the door twice" beats "I was afraid." A sound cue like "dry leaf cracking underfoot" beats "tense music."
4. **Showing over telling.** If a character explains the theme, delete the line. Let the images carry it.
5. **Subtext over statement.** Write what the character wants; let the reader deduce why.
6. **Exchange over monologue.** Every line should change what the next character says.
7. **Pilot before production.** Never render the full LTX phase before completing a 2-minute test scene end-to-end.
8. **User is the author.** This pipeline augments; it does not replace creative direction. Voice, theme, tone are the human's to lock. The agent proposes; the user disposes.

---

## 10. Pilot Protocol (Required Before Every Full Run)

Before committing the LTX phase (Phase 8, 8+ hours of machine time), render a **pilot scene** end-to-end:

1. Pick the single most important scene in the screenplay (usually the Act III turn or Act IV climax)
2. Run Phases 4→11 on that one scene only
3. Watch the pilot with the user
4. If the pilot fails, fix at the screenplay / voice / mix level, re-pilot
5. Only when the pilot is approved does the full render commence

The pilot is the single best investment of the whole project. It catches:
- Voice mis-casts
- Dialogue that doesn't work when spoken aloud
- Mix balance issues
- LTX motion failures
- Pacing that feels right on paper but drags on screen

---

## 11. Creative License — What's Fixed, What's Yours

This pipeline assumes a collaboration between human author and AI agent.
Some things are FIXED once decided (changing them mid-production wastes
work or breaks consistency). Other things are the agent's CHOICE within
the established frame. The agent should know which is which.

### 11.1 Locked After User Approval (do not modify without re-approval)

| Element | Why locked |
|---------|------------|
| **Character names** | Once said in dialogue, can't be changed without re-rendering every line that says them |
| **Character `voice_instruct` base + `voice_seed`** | Voice consistency across the whole episode |
| **Character `visual_tokens`** | Look consistency across all shots |
| **5-act spine + chosen plot template** | Restructuring mid-draft cascades into rewrites |
| **Plot twists committed to** | Plants are placed; payoff scenes are rendered; can't pull a twist after Act III is rendered |
| **Per-character color signature** | LTX prompts inherit; changing requires re-render |
| **Per-character lighting signature** | Same — re-render required |
| **The pilot scene's success criteria** | Define "good" before rendering, not after |

### 11.2 Agent's Creative License (assemble freely from blocks)

| Element | Agent decides |
|---------|---------------|
| **Specific dialogue wording** | Within character voice + scene goal, the exact words are the agent's craft |
| **Camera angle / movement / composition per shot** | Within the scene's emotional intent, choose deliberately |
| **Color/light specifics within character signature** | A character with "warm amber" can be lit warm-amber-soft or warm-amber-harsh per beat |
| **Cut type (hard / J / L / match / dissolve)** | Pick the cut that serves the moment |
| **Shot count per scene** | A 3-minute scene might be 8 shots or 25; agent's call within the scene's beat structure |
| **Music style vocabulary tags** | Within the chosen mood (sacred / climactic / silence), specific tags are agent choice |
| **SFX cue selection** | Per-scene cue list is agent's first draft; user reviews |
| **Verbal tics, speech rhythm specifics** | Within character speech pattern from character sheet |
| **T2V filler shot prompts** | With the locked style+location+character tokens prepended, the rest is craft |
| **Per-line `instruct_override`** | Within the character's `instruct_override_presets`, line-by-line direction is agent's |

### 11.3 Always Consult User Before

| Situation | Why |
|-----------|-----|
| Adding a new speaking character mid-production | Affects voice/visual budget, casting, story balance |
| Cutting a major character's scene | Story impact |
| Changing the central conflict | Affects everything |
| Adding or removing a plot twist | Affects planting work |
| Pivoting plot template mid-draft | Often means rewriting earlier acts |
| Going over runtime budget by >20% | Affects machine time |
| Changing music style for an act after it's rendered | Re-render cost |

### 11.4 The Agent's Default Posture

When in doubt:
1. **Propose, don't impose.** "I'd recommend X because Y. Want me to
   proceed, or adjust?"
2. **Save what works; iterate what doesn't.** Per-scene granularity means
   you can re-render one scene without losing others.
3. **Bias toward asking when the cost is high; bias toward acting when the
   cost is low.** A new SFX cue is cheap (try it). Changing a character's
   voice is expensive (ask first).
4. **The user is the author.** The pipeline augments. The film's voice is
   theirs.

---

## 12. Reference Materials — Where to Find, How to Use

Cinema is a derivative art. Every great film is in conversation with the
films, books, music, and visual traditions that came before it. The agent
should consciously place this project in that conversation.

### 12.1 On-Disk Source Material (use first)

Located in the workspace:

| Path | Type | Use for |
|------|------|---------|
| `ComfyUI/Divine_Self_Hermetic_Gnostic_Gnosis.md` | Philosophical compilation (Hermetica, Nag Hammadi, Thunder Perfect Mind, Song of the Pearl) | Mystical / spiritual / cosmological themes; direct quotation of short passages |
| `ComfyUI/The_Story_Organized/` | The Thinning Veil — visual novella, 10+ chapters of organized mystical narrative | Visual vocabulary, character archetypes, Egyptian/sacred motifs, descent-and-return narrative arcs |
| `ComfyUI/The_Story_Organized_Cropped/` | Same content, edited stills | Reference imagery |
| `ComfyUI/Suno Music/` | 13 tracks generated for prior projects | BYO music for moods that match track names |

**Reading discipline:**
1. Before drafting Act I, read the on-disk source material relevant to the
   project's tone. Don't skim — read for *voice and weight*.
2. Identify 3–5 specific passages, lines, or motifs from the sources that
   could land in the screenplay. Save them to
   `architecture/source_extracts.md` with attribution.
3. For each extract, decide: direct quote (in a character's mouth), or
   adapted (paraphrased into the project's voice), or absorbed (just shapes
   the agent's prose without showing).

### 12.2 Internal Skill References (the operational manual)

| Path | Use |
|------|-----|
| `memory/skills/qwen3-tts-voicedesign-comfyui.md` | TTS node schema, voice_instruct writing guide, prosody control |
| `memory/skills/ace-music-generation-comfyui.md` | ACE Step 1.5 music generation, parameter presets per mood |
| `memory/skills/ltx2-comfyui-i2v.md` | LTX 2.3 model inventory, image-to-video patterns, LoRA stack |
| `memory/skills/chatterbox-tts-comfyui.md` | Fallback TTS engine, when Qwen3-TTS unavailable |
| `memory/skills/comfyui-api-reference.md` | ComfyUI API endpoints, node submission patterns |
| `skills/Video-Creation-Techniques.md` | Parent skill doc, decision tree for pipeline path |

### 12.3 Film References — Cinema as Vocabulary

When the agent can't decide a stylistic question, ask: *what film does this
moment feel like?* Common touchstones:

| Film/Director | Useful for |
|---------------|------------|
| **Terrence Malick** (Tree of Life, Knight of Cups) | Voice-over musing, golden hour, slow camera drift, philosophical pacing |
| **2001: A Space Odyssey** (Kubrick) | Cosmic scale, classical composition, deliberate pacing, visual transcendence |
| **Stalker / Mirror** (Tarkovsky) | Long takes, slow movement, dream logic, time as substance |
| **In the Mood for Love** (Wong Kar-wai) | Restrained dialogue, repeated motifs, color as emotion |
| **Arrival** (Villeneuve) | Memory and time-twist structure, language as theme, restrained score |
| **The Mirror** (Tarkovsky) | Memory braided with present; non-linear emotional logic |
| **Hereditary / Midsommar** (Aster) | Slow dread, ritual atmosphere, color saturation as emotional escalation |
| **Annihilation** (Garland) | Dissolution-of-self imagery, biological/cosmic horror, jewel-tone palette |
| **The Fountain** (Aronofsky) | Three time periods braided, mortality, sacred geometry, golden imagery |
| **Pi** (Aronofsky) | Obsession with pattern, sacred mathematics, monochromatic intensity |
| **Sunset Blvd** (Wilder) | Frame-story narration, retrospective POV, the dead telling their own story |
| **Pan's Labyrinth** (del Toro) | Mythic/political braided, child-as-protagonist of cosmic stakes |
| **The Witch** (Eggers) | Slow build, period dialect, ambient music, dread without jump scares |

The agent should **not imitate** these films — but should consciously
*echo* their craft choices when those choices serve the material.

### 12.4 Musical References — Score Vocabulary

When writing music style tags, having a reference helps:

| Composer/Style | Useful for |
|----------------|------------|
| **Jóhann Jóhannsson** (Arrival, Sicario) | Restrained orchestral, drones, sub-bass, contemporary cinematic |
| **Hildur Guðnadóttir** (Joker, Chernobyl) | Cello drones, darkness, sustained tension, sparse |
| **Nils Frahm** | Solo piano + tape texture, intimate, contemplative |
| **Max Richter** | String-led minimalism, melancholy, repeating motifs |
| **Mica Levi** (Under the Skin, Jackie) | Otherworldly strings, dissonance, alien textures |
| **Brian Eno** (ambient series) | Environmental, drone-based, no rhythm, infinite duration |
| **Jonny Greenwood** (There Will Be Blood, The Master) | Violent strings, dissonance, period-modern hybrid |
| **Hans Zimmer** (Interstellar, Inception) | Organ-led grandeur, BRAAAM, pulse-driven epic |
| **Clint Mansell** (The Fountain, Requiem) | Strings + grief, layered build, repeating mournful theme |
| **Sigur Rós** (Hopelandic, ambient) | Bowed guitar, ethereal vocal, slow build, post-rock cinematic |

When writing ACE Step `tags`, you can echo these ("orchestral minimalism in
the style of Max Richter, cello drone with sparse piano") — ACE will
approximate the texture even if not the exact composer.

### 12.5 Visual / Painting References

For LTX prompts and color palettes:

| Artist / Movement | Useful for |
|-------------------|------------|
| **Caravaggio** (chiaroscuro) | Dramatic single-source light, shadow-heavy, baroque tension |
| **Hilma af Klint** | Sacred geometry, mystical color, abstract spiritual |
| **Alex Grey** | Visionary art, anatomy + cosmos, layered transparency |
| **William Blake** | Mythic figures, prophetic imagery, archetypal |
| **Hieronymus Bosch** | Dense composition, surreal scale, cosmic + grotesque |
| **Wassily Kandinsky** | Color as emotion, geometric abstraction |
| **Mark Rothko** | Color field, contemplative scale, emotional weight |
| **Studio Ghibli** | Soft natural light, painted skies, luminous greens |
| **Gerhard Richter** (squeegee paintings) | Smeared color, ambiguous form, emotional saturation |

Useful in LTX/Flux prompts: "in the style of Hilma af Klint", "Caravaggio
chiaroscuro lighting", "Mark Rothko color field"…

### 12.6 Adaptation Rules — Honoring Sources

When borrowing from any source (text, film, music, image):

1. **Direct quotation: short and attributed (in the screenplay's metadata).**
   Lines under 10 words from public-domain texts (Hermetica, Gnostic
   Gospels, Bible, Bhagavad Gita, public-domain literature) can appear in
   characters' mouths verbatim. Note the source in the screenplay's `_meta`
   block.
2. **Paraphrasing: free.** Lift the *idea*, write it in the project's voice.
3. **Stylistic echo: free.** "A scene in the rhythm of Tarkovsky's
   bath-house" is fine; you don't owe Tarkovsky for emulating his pacing.
4. **Modern copyrighted material: never quote verbatim, only echo.**
   No lifting actual lines from films, songs, or copyrighted books.
5. **Visual style: always free to echo.** Lighting, palette, composition
   borrowing is craft, not infringement.

### 12.7 Building a Project's Reference Library

Before drafting, create `architecture/reference_library.md` that lists:

```markdown
# References for [PROJECT NAME]

## Source Texts (on-disk)
- Path → what it provides
- Path → what it provides

## Tonal Films (the films this aspires to feel like)
- Film → specific element borrowed (pacing? color? structure?)

## Musical Touchstones
- Composer/track → which scene mood

## Visual Touchstones
- Artist/movement → which palette or composition

## Specific Quotes Considered
- "..." — source — character who would speak it (if any)
```

This document is the agent's compass when style decisions get foggy.
Update it as the project evolves.

---

## 13. Internal Skill Cross-Links

- `memory/skills/qwen3-tts-voicedesign-comfyui.md`
- `memory/skills/ace-music-generation-comfyui.md`
- `memory/skills/ltx2-comfyui-i2v.md`
- `memory/skills/chatterbox-tts-comfyui.md`
- `memory/skills/comfyui-api-reference.md`
- `skills/Video-Creation-Techniques.md`
