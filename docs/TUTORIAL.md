# Tutorial: one video from start to upload

This walkthrough makes one vertical video with ARGUS in the Kiro chat. It uses the graphics path,
which needs no AI keys. Install first: [INSTALL.md](../INSTALL.md).

Each step names the tool, what to check, and what you decide. The model proposes; you approve at the
checkpoints.

## Step 1. Check the setup

Ask: `Call studio_guide and follow its working order.`

`studio_guide` returns the tools, the providers that work on this machine, and your saved
preferences. If a provider is missing, it says what to install.

## Step 2. Write the script

Ask: `Write a 20-second script about why most beginners stop editing after the second week. Hook in the first 1.5 seconds, three beats, a call to action.`

Read it, then approve or ask for changes. Nothing is voiced or rendered before you approve.

## Step 3. Choose the picture

The model writes a plan: scenes such as `words`, `title`, `counter` and `cta`, with times in
seconds. Show the plan and the reason for it, then get approval.

## Step 4. Voice

Ask: `Use voice_options to list voices, pick one for this script, and tell me why.`

Then: `Voice the script with synthesize_voiceover, project tutorial.` Without keys, the voice is edge
(free). The result is `audio/voice.mp3` and `audio/voice.words.json` in the project folder, with a
word list that has start and end times. Check that the duration matches the script's length.

## Step 5. Stills first

Ask: `Render stills of the plan at 1, 4 and 8 seconds, project tutorial, mode stills.`

The model looks at each picture. Check the text: nothing cut off at the edges, captions readable,
accent words where you expect them. Say what to change, and repeat this step until the frames look
right. Stills are cheap, so fix problems here rather than in the final render.

## Step 6. Preview, then final

Ask: `Render a preview, then the final render, 9:16.`

Long renders return a `job_id`. Ask for `job_status` until the state is `done`.

## Step 7. Check

Ask: `Run qa_verify_video on the final file.`

The result lists the technical checks and attaches frames. A hard failure (for example a true peak
above the limit or a black gap longer than one second in the middle) stops the export. A warning
(for example a short black gap or a platform length limit) is shown, and you decide what to do with it.

## Step 8. Export

Ask: `Run export_package for tutorial.`

The upload folder holds the video, the covers and `post.md` with the title, description and
hashtags. Publishing is manual: ARGUS does not call any platform API.
