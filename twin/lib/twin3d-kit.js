/* ============================================================================
   twin3d-kit.js  ·  ESP32 Fleet Digital Twins — shared 3D scaffolding
   ----------------------------------------------------------------------------
   Two reusable pieces every twin's 3D view needs, extracted from the grid twin
   so water / datacenter / pipeline / etc. inherit them instead of re-deriving:

     1) Twin3D.addLighting(scene)      — the BRIGHT baseline (fixes dark scenes)
     2) Twin3D.createOrbitNav(...)     — drag-orbit + nav pad (presets, zoom,
                                          rotate, RESET, CENTER-to-fit)

   No build step. Requires THREE (r128) already loaded globally. Vanilla JS.

   ── Why this exists ─────────────────────────────────────────────────────────
   Default three.js scenes on this project keep coming out too dark: dim ambient,
   near-black PBR metals with nothing to catch, and fog that eats the far geometry.
   addLighting() is the corrected floor — start here, don't darken back out of it.

   ── Minimal usage ───────────────────────────────────────────────────────────
     <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
     <script src="twin3d-kit.js"></script>
     ...
     const scene   = new THREE.Scene();
     const camera  = new THREE.PerspectiveCamera(45, 1, 0.1, 2000);
     Twin3D.addLighting(scene);                 // ← bright baseline + fog

     const content = new THREE.Group();          // put EQUIPMENT here (not ground)
     scene.add(content);                         // CENTER frames this, not the grid
     // ... add busbars / tanks / pumps / racks to `content` ...

     const nav = Twin3D.createOrbitNav({
       THREE, camera,
       dom: document.getElementById('glWrap'),   // the element receiving pointer events
       navpadEl: document.getElementById('navpad'), // optional; auto-created if omitted
       focus: () => content,                     // what CENTER / initial fit frames
       // home: {az:-0.9, el:0.55, r:340, tx:10, ty:40, tz:0}, // optional custom home
     });

     function frame(){ nav.update(); renderer.render(scene, camera); requestAnimationFrame(frame); }
     // call nav.setVisible(true/false) when you toggle in/out of the 3D view.

   ── CSS ─────────────────────────────────────────────────────────────────────
   Twin3D.navpadCSS() returns the stylesheet string for the pad; inject once:
     const s=document.createElement('style'); s.textContent=Twin3D.navpadCSS();
     document.head.appendChild(s);
   (Uses the shared twin CSS vars: --panel,--line,--ink,--ink-dim,--phase-b.)
============================================================================ */
(function (global) {
  'use strict';
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));

  /* ---- 1) Lighting: the bright baseline ---------------------------------- */
  function addLighting(scene, opts = {}) {
    const T = global.THREE;
    const o = Object.assign({
      ambient: 1.15, hemi: 0.9, key: 1.35, fill: 0.55, rim: 0.55,
      fog: 0.0025, fogColor: 0x0a0e14,
      keyColor: 0xdcecff, fillColor: 0x9fc2ff, rimColor: 0x3bd6f2,
      ambientColor: 0x9fb4d0, hemiSky: 0xbfe0ff, hemiGround: 0x1a2536,
    }, opts);

    if (o.fog) scene.fog = new T.FogExp2(o.fogColor, o.fog);
    scene.add(new T.AmbientLight(o.ambientColor, o.ambient));
    scene.add(new T.HemisphereLight(o.hemiSky, o.hemiGround, o.hemi)); // sky/ground fill
    const key  = new T.DirectionalLight(o.keyColor,  o.key);  key.position.set(90, 150, 70);
    const fill = new T.DirectionalLight(o.fillColor, o.fill); fill.position.set(-60, 80, 90);
    const rim  = new T.DirectionalLight(o.rimColor,  o.rim);  rim.position.set(-90, 50, -70);
    scene.add(key, fill, rim);
    return { key, fill, rim };
  }

  /* Material helper: keep equipment metals light enough to catch the fill.
     Rule of thumb learned on the grid twin — nothing darker than ~#2c-#4a base. */
  function equipMaterial(color, extra = {}) {
    return new global.THREE.MeshStandardMaterial(
      Object.assign({ color, metalness: 0.45, roughness: 0.55 }, extra));
  }

  /* ---- 2) Orbit + nav pad ------------------------------------------------ */
  const DEFAULT_VIEWS = {
    iso:   { az: -0.9,          el: 0.55, r: 340 },
    front: { az: -Math.PI / 2,  el: 0.14, r: 330 },
    top:   { az: -Math.PI / 2,  el: 1.32, r: 360 },
    side:  { az: 0,             el: 0.20, r: 330 },
  };
  const DEFAULT_HOME = { az: -0.9, el: 0.55, r: 340, tx: 10, ty: 40, tz: 0 };

  function buildNavpad(el) {
    el.classList.add('navpad');
    el.innerHTML = `
      <div class="navrow">
        <button data-view="iso"   title="Isometric">ISO</button>
        <button data-view="front" title="Front elevation">FRONT</button>
        <button data-view="top"   title="Plan / top-down">TOP</button>
        <button data-view="side"  title="Side">SIDE</button>
      </div>
      <div class="navrow">
        <button data-nav="in"   title="Zoom in">＋</button>
        <button data-nav="out"  title="Zoom out">－</button>
        <button data-nav="rotl" title="Rotate left">↺</button>
        <button data-nav="rotr" title="Rotate right">↻</button>
        <button data-nav="center" title="Center model in view">CENTER</button>
        <button data-nav="reset"  title="Reset view" class="wide">RESET</button>
      </div>`;
  }

  function createOrbitNav(cfg) {
    const T = cfg.THREE || global.THREE;
    const camera = cfg.camera;
    const dom = cfg.dom;
    const rMin = cfg.rMin || 140, rMax = cfg.rMax || 620;
    const HOME = Object.assign({}, DEFAULT_HOME, cfg.home);
    const VIEWS = Object.assign({}, DEFAULT_VIEWS, cfg.views);
    const focus = cfg.focus || (() => null); // () => Object3D | Box3

    let orb = Object.assign({}, HOME);
    let target = null;                        // when set, ease orb toward it

    // nav pad element (create one if not supplied)
    let pad = cfg.navpadEl;
    if (!pad) { pad = document.createElement('div'); (cfg.mount || document.body).appendChild(pad); }
    buildNavpad(pad);

    function goView(v) { const p = VIEWS[v] || {}; target = Object.assign({}, orb, p); }
    function centerView() {
      const f = focus(); if (!f) return;
      const box = (f.isBox3) ? f.clone() : new T.Box3().setFromObject(f);
      if (box.isEmpty()) return;
      const c = box.getCenter(new T.Vector3());
      const sph = box.getBoundingSphere(new T.Sphere());
      const fov = T.MathUtils.degToRad(camera.fov);
      const fit = sph.radius / Math.sin(fov / 2) * (cfg.fitMargin || 1.15);
      target = Object.assign({}, orb, { tx: c.x, ty: c.y, tz: c.z, r: clamp(fit, rMin, rMax) });
    }
    function nudge(k) {
      target = null;
      if (k === 'in')   orb.r = clamp(orb.r - 45, rMin, rMax);
      if (k === 'out')  orb.r = clamp(orb.r + 45, rMin, rMax);
      if (k === 'rotl') orb.az -= 0.28;
      if (k === 'rotr') orb.az += 0.28;
      if (k === 'reset') target = Object.assign({}, HOME);
    }

    // drag-orbit + wheel-zoom
    let dragging = false, px = 0, py = 0;
    dom.addEventListener('pointerdown', e => {
      if (e.target.closest('.navpad')) return;
      dragging = true; px = e.clientX; py = e.clientY; target = null;
    });
    window.addEventListener('pointermove', e => {
      if (!dragging) return;
      orb.az -= (e.clientX - px) * 0.006;
      orb.el = clamp(orb.el - (e.clientY - py) * 0.005, 0.12, 1.35);
      px = e.clientX; py = e.clientY;
    });
    window.addEventListener('pointerup', () => dragging = false);
    dom.addEventListener('wheel', e => {
      e.preventDefault(); target = null;
      orb.r = clamp(orb.r + e.deltaY * 0.4, rMin, rMax);
    }, { passive: false });

    // pad clicks
    pad.addEventListener('click', e => {
      const b = e.target.closest('button'); if (!b) return;
      if (b.dataset.view) goView(b.dataset.view);
      else if (b.dataset.nav === 'center') centerView();
      else if (b.dataset.nav) nudge(b.dataset.nav);
    });

    // call once per frame
    function update() {
      if (target) {
        const k = 0.15; let done = true;
        for (const key of ['az', 'el', 'r', 'tx', 'ty', 'tz']) {
          orb[key] += (target[key] - orb[key]) * k;
          if (Math.abs(target[key] - orb[key]) > 0.002) done = false;
        }
        if (done) { Object.assign(orb, target); target = null; }
      }
      const { az, el, r, tx, ty, tz } = orb;
      camera.position.set(tx + r * Math.cos(el) * Math.cos(az),
                          ty + r * Math.sin(el),
                          tz + r * Math.cos(el) * Math.sin(az));
      camera.lookAt(tx, ty, tz);
    }

    return {
      update, goView, centerView, nudge, pad, orb,
      setVisible(on) { pad.classList.toggle('on', !!on); },
      setHome(h) { Object.assign(HOME, h); },
    };
  }

  function navpadCSS() {
    return `
.navpad{position:absolute;right:16px;bottom:14px;display:none;flex-direction:column;gap:7px;align-items:flex-end}
.navpad.on{display:flex}
.navrow{display:flex;gap:6px}
.navpad button{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.5px;
  min-width:34px;height:30px;padding:0 8px;cursor:pointer;color:var(--ink-dim,#7d8da0);
  background:rgba(15,21,30,.82);border:1px solid var(--line,#1e2a3a);border-radius:7px;
  backdrop-filter:blur(6px);transition:.12s}
.navpad button:hover{color:var(--ink,#dbe6f2);border-color:var(--phase-b,#3bd6f2);background:rgba(19,27,38,.92)}
.navpad button:active{transform:translateY(1px)}
.navpad button.wide{min-width:52px}`;
  }

  global.Twin3D = { addLighting, equipMaterial, createOrbitNav, navpadCSS,
                    DEFAULT_VIEWS, DEFAULT_HOME };
})(typeof window !== 'undefined' ? window : this);
