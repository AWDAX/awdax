# Tutorial video

The app shows one tutorial video. It opens by itself the first time a signed-in user opens `/app`, and every "Watch tutorial" button opens it again. The landing page has no tutorial.

## Where the file goes

Pick one:

- Put the file at `Frontend/public/tutorial/awdax-tutorial.mp4`. It is served from `/tutorial/awdax-tutorial.mp4`.
- Or host it elsewhere and set `VITE_TUTORIAL_VIDEO_URL` to the direct file URL (build-time env var).

Until a file exists, the dialog shows "The tutorial video isn't available yet."

## Format

MP4, H.264 video + AAC audio, 1920x1080, 30 fps, with `faststart` so it plays before it finishes downloading:

```bash
ffmpeg -i input.mov -c:v libx264 -crf 23 -preset slow -c:a aac -b:a 128k -movflags +faststart awdax-tutorial.mp4
```

**Cloudflare Pages rejects files over 25 MiB.** If the video is longer or heavier than that, host it elsewhere (for example R2, or an unlisted direct file link) and point `VITE_TUTORIAL_VIDEO_URL` at it.

## Suggested chapters

1. Sign in
2. New chat: the prompt, example cards, uploading a file
3. Plan review and approve
4. Live run: sources, rows streaming in, pause and resume, row alerts
5. Chat data view: report, data, graphs and sources tabs, export, ask
6. Sidebar: search, rename, delete with undo
7. Projects page and project report
8. Ask database

## Testing the first-run popup

It opens once per user. To see it again, remove the `awdax.tutorial.seen.v1:<user id>` key from localStorage (`awdax.tutorial.seen.v1:anon` in `--mode agent`) and reload `/app`.
