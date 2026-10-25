// vdo Google Flow helper - paste this whole file into the browser tool's "run JavaScript" on a
// flow.google.com project page. It adds window.vdo with small functions Claude calls between prompts.
//
//   vdo.snapshot()                 remember which pictures are on the page now
//   await vdo.waitIdle()           wait until no tile is still generating (shows "NN%")
//   await vdo.fresh()              pictures added since the snapshot, newest first: [{uuid, src}]
//   await vdo.save(map, project)   map = {"s02_bg": "<uuid>", ...}; downloads each as
//                                  vdo__<project>__<id>.jpg into the browser's Downloads folder
//   await vdo.pack(map)            same pictures as base64 kept in the page (for remote sessions);
//                                  then read them with vdo.chunk(i) - each chunk < 250k characters
(() => {
  const isPic = (im) => im.naturalWidth >= 500 && /flow-content\.google\/image\//.test(im.src);
  const uuidOf = (src) => (src.match(/image\/([0-9a-f-]{36})/) || [])[1];
  const scroller = () => [...document.querySelectorAll('*')]
    .filter((e) => e.scrollHeight > e.clientHeight + 50 && /(auto|scroll)/.test(getComputedStyle(e).overflowY))
    .sort((a, b) => b.scrollHeight - a.scrollHeight)[0] || document.scrollingElement;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  async function scan(maxScroll = 6000) {
    // the gallery is virtualised: scroll through it and record every picture with its position
    const s = scroller();
    const seen = new Map();
    const keep = s.scrollTop;
    for (let y = 0; y <= Math.min(maxScroll, s.scrollHeight); y += Math.max(200, s.clientHeight * 0.6)) {
      s.scrollTop = y;
      await sleep(350);
      for (const im of document.querySelectorAll('img')) {
        if (!isPic(im)) continue;
        const id = uuidOf(im.src);
        if (!id || seen.has(id)) continue;
        const r = im.getBoundingClientRect();
        seen.set(id, { uuid: id, src: im.src, top: r.top + s.scrollTop, left: r.left });
      }
    }
    s.scrollTop = keep;
    return [...seen.values()].sort((a, b) => a.top - b.top || a.left - b.left); // newest first
  }

  const busy = () => [...document.querySelectorAll('div,span')]
    .some((e) => e.children.length === 0 && /^\d{1,3}%$/.test(e.textContent.trim()));

  async function blobOf(src) {
    const r = await fetch(src);
    if (!r.ok) throw new Error('fetch failed ' + r.status);
    return r.blob();
  }

  window.vdo = {
    known: new Set(),
    packed: '',
    async snapshot() {
      const all = await scan();
      this.known = new Set(all.map((x) => x.uuid));
      return this.known.size;
    },
    async waitIdle(timeoutMs = 240000) {
      const t0 = Date.now();
      await sleep(1500);
      while (busy() && Date.now() - t0 < timeoutMs) await sleep(2000);
      await sleep(1500);
      return !busy();
    },
    async fresh() {
      const all = await scan();
      this.last = all.filter((x) => !this.known.has(x.uuid));
      return this.last.map((x) => ({ uuid: x.uuid }));
    },
    // jobs: ids in the order their prompts were SUBMITTED; per: pictures per prompt (Flow "x2" = 2)
    assign(jobs, per = 2) {
      const list = this.last || [];
      if (list.length !== jobs.length * per) {
        return { ok: false, reason: `expected ${jobs.length * per} new pictures, found ${list.length}` };
      }
      const map = {}, alts = {};
      jobs.forEach((id, j) => {
        const group = list.slice((jobs.length - 1 - j) * per, (jobs.length - j) * per);
        map[id] = group[0].uuid;
        alts[id] = group.map((g) => g.uuid);
      });
      this.map = map;
      return { ok: true, map, alts };
    },
    srcOf(uuid) {
      const hit = [...document.querySelectorAll('img')].find((im) => uuidOf(im.src) === uuid);
      if (hit) return hit.src;
      const m = (this.last || []).find((x) => x.uuid === uuid);
      return m && m.src;
    },
    async save(map, project) {
      const done = [];
      for (const [id, uuid] of Object.entries(map || this.map)) {
        const b = await blobOf(this.srcOf(uuid));
        const ext = b.type.includes('png') ? 'png' : 'jpg';
        const a = document.createElement('a');
        a.href = URL.createObjectURL(b);
        a.download = `vdo__${project}__${id}.${ext}`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        done.push(a.download);
        await sleep(400);
      }
      return done;
    },
    async pack(map) {
      const parts = [];
      for (const [id, uuid] of Object.entries(map || this.map)) {
        const b = await blobOf(this.srcOf(uuid));
        const data = await new Promise((r) => { const f = new FileReader(); f.onload = () => r(f.result.split(',')[1]); f.readAsDataURL(b); });
        parts.push(id + ':' + data);
      }
      this.packed = parts.join('\n');
      return { chars: this.packed.length, chunks: Math.ceil(this.packed.length / 240000) };
    },
    chunk(i) {
      return 'VDOCHUNK' + i + '|' + this.packed.slice(i * 240000, (i + 1) * 240000);
    },
  };
  return 'vdo helper ready';
})();
