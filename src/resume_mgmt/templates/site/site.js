// Experience filter (domain tiles, skill chips, free-text query), folding of long roles, the career
// track's detail line, and the light/dark toggle. Without JavaScript every item stays visible, the filter controls stay
// hidden, and the track's marks fall back to their <title> tooltips.
(function () {
  "use strict";

  var root = document.documentElement;
  root.classList.add("js");
  var themeBtn = document.querySelector(".theme");
  function storedTheme() {
    try { return localStorage.getItem("theme"); } catch (e) { return null; }
  }
  var saved = storedTheme();
  if (saved === "light" || saved === "dark") root.setAttribute("data-theme", saved);
  if (themeBtn) {
    themeBtn.hidden = false;
    themeBtn.addEventListener("click", function () {
      var dark = root.getAttribute("data-theme") === "dark" ||
        (!root.hasAttribute("data-theme") && window.matchMedia("(prefers-color-scheme: dark)").matches);
      var next = dark ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("theme", next); } catch (e) { /* private mode */ }
    });
  }

  // Career track: hover, focus or tap a mark to show its detail line. Starts on the current role.
  var track = document.querySelector(".track");
  var detail = track && track.querySelector(".tk-detail");
  if (detail) {
    var marks = Array.prototype.slice.call(track.querySelectorAll(".tk-hit"));
    var showMark = function (mark) {
      // Both drawings carry the same marks; highlight the match in each.
      marks.forEach(function (m) {
        m.classList.toggle("on", m.getAttribute("data-detail") === mark.getAttribute("data-detail"));
      });
      detail.firstChild.textContent = mark.getAttribute("data-detail");
      detail.lastChild.textContent = mark.getAttribute("data-dates");
    };
    var pick = function (ev) {
      var mark = ev.target.closest && ev.target.closest(".tk-hit");
      if (mark) showMark(mark);
    };
    ["mouseover", "focusin", "click"].forEach(function (type) { track.addEventListener(type, pick); });
    var current = track.querySelector(".tk-current");
    if (current) showMark(current);
    detail.hidden = false;
  }

  var timeline = document.querySelector(".timeline");
  if (!timeline) return;
  var filters = document.querySelector(".filters");
  if (filters) filters.hidden = false;

  var active = { domain: "", skill: "", text: "" };
  var items = Array.prototype.slice.call(timeline.querySelectorAll(".item"));
  var roles = Array.prototype.slice.call(timeline.querySelectorAll(".role"));
  var empty = timeline.querySelector(".empty-state");
  var status = filters && filters.querySelector(".filter-status");
  var input = filters && filters.querySelector("#q");
  var controls = Array.prototype.slice.call(document.querySelectorAll("[data-kind]"));
  var haystack = items.map(function (item) { return item.textContent.toLowerCase(); });
  var tags = Array.prototype.slice.call(timeline.querySelectorAll(".item .tag"));

  function matches(item, i) {
    var domains = (item.getAttribute("data-domains") || "").split(" ");
    var skills = (item.getAttribute("data-skills") || "").split(" ");
    return (!active.domain || domains.indexOf(active.domain) !== -1) &&
           (!active.skill || skills.indexOf(active.skill) !== -1) &&
           (!active.text || haystack[i].indexOf(active.text) !== -1);
  }

  function token(text) {
    var span = document.createElement("span");
    span.className = "tok";
    span.textContent = text;
    return span;
  }

  // Long roles show their first few highlights; the rest wait behind "show N more". A filter
  // shows every match regardless and hides the toggles; clearing it restores each role's state.
  var folds = Array.prototype.slice.call(timeline.querySelectorAll(".role-more"));
  folds.forEach(function (btn) {
    var list = document.getElementById(btn.getAttribute("aria-controls"));
    var preview = Number(list.getAttribute("data-preview"));
    Array.prototype.slice.call(list.children).forEach(function (item, i) {
      if (i >= preview) item.classList.add("extra");
    });
    btn.closest(".role").classList.add("folded");
  });

  function setFold(btn, open) {
    btn.closest(".role").classList.toggle("folded", !open);
    btn.setAttribute("aria-expanded", String(open));
    btn.textContent = open ? "show fewer" : btn.getAttribute("data-more");
  }

  // A link into a folded role (career track, capabilities page, #fragment) opens it first.
  function reveal(hash) {
    var id = hash && decodeURIComponent(hash.slice(1));
    var target = id && document.getElementById(id);
    var role = target && target.closest(".role.folded");
    if (role) setFold(role.querySelector(".role-more"), true);
  }
  reveal(location.hash);
  window.addEventListener("hashchange", function () { reveal(location.hash); });

  function apply() {
    var filtering = active.domain || active.skill || active.text;
    timeline.classList.toggle("filtering", Boolean(filtering));
    var shown = 0;
    items.forEach(function (item, i) {
      var ok = matches(item, i);
      item.classList.toggle("filtered-out", !ok);
      if (ok) shown += 1;
    });
    roles.forEach(function (role) {
      var visible = role.querySelectorAll(".item:not(.filtered-out)").length;
      role.classList.toggle("filtered-out", Boolean(filtering) && visible === 0);
    });
    if (empty) empty.hidden = !filtering || shown > 0;
    // Mark the skill tags that match the active skill or query.
    tags.forEach(function (tag) {
      var hit = (active.skill && tag.getAttribute("data-skill") === active.skill) ||
                (active.text && tag.textContent.toLowerCase().indexOf(active.text) !== -1);
      tag.classList.toggle("hit", Boolean(hit));
    });
    controls.forEach(function (c) {
      c.setAttribute("aria-pressed", String(c.getAttribute("data-value") === active[c.getAttribute("data-kind")]));
    });
    if (!status) return;
    status.textContent = "";
    if (!filtering) return;
    if (active.domain) status.appendChild(token("domain:" + active.domain));
    if (active.skill) status.appendChild(token("skill:" + active.skill));
    if (active.text) status.appendChild(token('"' + active.text + '"'));
    status.appendChild(document.createTextNode(shown + " of " + items.length + " highlights"));
    var clear = document.createElement("button");
    clear.type = "button";
    clear.textContent = "clear";
    clear.addEventListener("click", function () {
      active = { domain: "", skill: "", text: "" };
      if (input) input.value = "";
      apply();
    });
    status.appendChild(clear);
  }

  var more = filters && filters.querySelector(".chip-more");
  var moreLabel = more ? more.textContent : "";
  if (more) more.parentNode.classList.add("collapsed");

  document.addEventListener("click", function (ev) {
    if (more && ev.target === more) {
      var collapsed = more.parentNode.classList.toggle("collapsed");
      more.setAttribute("aria-expanded", String(!collapsed));
      more.textContent = collapsed ? moreLabel : "Fewer";
      return;
    }
    var fold = ev.target.closest(".role-more");
    if (fold) {
      var open = fold.getAttribute("aria-expanded") !== "true";
      setFold(fold, open);
      // Folding a long role from its foot can leave the reader far below it; bring the toggle back.
      if (!open && fold.getBoundingClientRect().top < 0) fold.scrollIntoView({ block: "center" });
      return;
    }
    // Same-page links open their target's role before the browser scrolls to it.
    var link = ev.target.closest("a[href^='#']");
    if (link) reveal(link.getAttribute("href"));
    var control = ev.target.closest("[data-kind]");
    if (!control) return;
    var kind = control.getAttribute("data-kind");
    var value = control.getAttribute("data-value");
    // Clicking the active control again clears that filter.
    active[kind] = active[kind] === value ? "" : value;
    apply();
    if (kind === "domain") document.getElementById("experience").scrollIntoView({ block: "start" });
  });

  if (input) {
    input.addEventListener("input", function () {
      active.text = input.value.trim().toLowerCase();
      apply();
    });
    // "/" focuses the filter, as in most developer tools.
    document.addEventListener("keydown", function (ev) {
      var tag = (ev.target.tagName || "").toLowerCase();
      if (ev.key === "/" && tag !== "input" && tag !== "textarea" && !ev.metaKey && !ev.ctrlKey) {
        ev.preventDefault();
        input.focus();
      } else if (ev.key === "Escape" && ev.target === input) {
        input.value = "";
        active.text = "";
        apply();
      }
    });
  }
})();
