/* America.co Public Tools, static edition. No dependencies. Nothing typed here is sent anywhere or saved. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var base = (document.querySelector('meta[name="site-base"]') || {}).content || "";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function download(name, text) {
    var link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function () { URL.revokeObjectURL(link.href); }, 2000);
  }
  function copy(text, done, failed) {
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, failed);
    else failed();
  }
  /* Today's date in Washington, D.C., as YYYY-MM-DD: comment periods close on Eastern time. */
  function easternToday() {
    try {
      var p = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
      var o = {};
      p.forEach(function (x) { o[x.type] = x.value; });
      return o.year + "-" + o.month + "-" + o.day;
    } catch (e) { return new Date().toISOString().slice(0, 10); }
  }
  function dayNumber(iso) { var p = iso.split("-"); return Math.round(Date.UTC(+p[0], +p[1] - 1, +p[2]) / 864e5); }
  function shortDate(iso) {
    var p = iso.split("-");
    return ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][+p[1] - 1] + " " + (+p[2]) + ", " + p[0];
  }
  function leftLabel(closes, today) {
    var n = dayNumber(closes) - dayNumber(today);
    return n === 0 ? "closes today" : n === 1 ? "closes tomorrow" : n > 1 ? n + " days left" : "closed";
  }

  /* ------------------------------------------------------------------ the taxpayer receipt */
  var dataEl = $("receipt-data"), form = $("receipt-form");
  if (dataEl && form && typeof BigInt === "function") {
    var data = JSON.parse(dataEl.textContent);
    var input = $("amount"), rowsEl = $("receipt-rows"), statusEl = $("receipt-status");
    var MAX = BigInt(data.max) * 100n;

    var toCents = function (text) {
      var clean = String(text).replace(/[^0-9.]/g, ""), parts = clean.split(".");
      var dollars = parts[0].replace(/^0+(?=\d)/, "") || "0", frac = ((parts[1] || "") + "00").slice(0, 2);
      if (dollars.length > 12) return MAX;
      var c = BigInt(dollars) * 100n + BigInt(frac);
      return c > MAX ? MAX : c;
    };
    var usd = function (c) {
      var neg = c < 0n, a = neg ? -c : c, d = (a / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ","), f = (a % 100n).toString();
      return (neg ? "-$" : "$") + d + "." + (f.length < 2 ? "0" + f : f);
    };
    /* The same steps as civictools/receipt.py: round each share down to the cent, then hand the cents
       left over to the lines with the largest remainders, so the parts sum to the amount entered. */
    var allocate = function (amount, lines) {
      var total = lines.reduce(function (s, c) { return s + c; }, 0n);
      var floors = [], rems = [];
      lines.forEach(function (c) {
        var prod = amount * c, q = prod / total, r = prod % total;
        if (r < 0n) { q -= 1n; r += total; }           /* floor division, also for negative lines */
        floors.push(q); rems.push(r);
      });
      var left = amount - floors.reduce(function (s, c) { return s + c; }, 0n);
      var order = lines.map(function (_, i) { return i; }).sort(function (a, b) { return rems[a] === rems[b] ? a - b : (rems[a] > rems[b] ? -1 : 1); });
      for (var i = 0; i < Number(left); i++) floors[order[i]] += 1n;
      return floors;
    };
    var view = function () { var r = form.querySelector('input[name="view"]:checked'); return r ? r.value : "purpose"; };
    var current = function () {
      var v = data.views[view()] || data.views.purpose, lines = v.lines.map(function (l) { return BigInt(l[1]); });
      var amount = toCents(input.value), parts = allocate(amount, lines);
      var total = lines.reduce(function (s, c) { return s + c; }, 0n);
      return { v: v, lines: lines, amount: amount, parts: parts, total: total };
    };
    var share = function (c, total) {                 /* one decimal place, rounded half up, exact */
      var neg = c < 0n, x = ((neg ? -c : c) * 10000n / total + 5n) / 10n;
      return (neg ? "-" : "") + (x / 10n).toString() + "." + (x % 10n).toString() + "%";
    };
    var render = function () {
      var s = current(), top = s.lines.reduce(function (m, c) { var a = c < 0n ? -c : c; return a > m ? a : m; }, 1n);
      rowsEl.innerHTML = s.v.lines.map(function (l, i) {
        var c = s.lines[i], a = c < 0n ? -c : c, width = Number(a * 10000n / top) / 100;
        var name = l[2] ? '<a href="' + base + "/taxpayer-receipt/" + esc(l[2]) + '/">' + esc(l[0]) + "</a>" : esc(l[0]);
        return '<div class="row' + (c < 0n ? " neg" : "") + '"><span class="what">' + name + " <small>" + share(c, s.total) + '</small></span><span class="amt">' +
          usd(s.parts[i]) + '</span><span class="bar"><i style="width:' + width.toFixed(2) + '%"></i></span></div>';
      }).join("");
      $("receipt-total").textContent = usd(s.amount);
      $("receipt-sum").textContent = usd(s.parts.reduce(function (x, c) { return x + c; }, 0n));
      $("receipt-view").textContent = s.v.label;
      document.documentElement.setAttribute("data-receipt", s.amount.toString() + ":" + view());
    };
    var shareLink = function () {
      var s = current(), dollars = (s.amount / 100n).toString() + (s.amount % 100n ? "." + ("0" + (s.amount % 100n).toString()).slice(-2) : "");
      return data.base + "/taxpayer-receipt/#amount=" + dollars + (view() === "agency" ? "&view=agency" : "");
    };
    var say = function (text) { if (statusEl) { statusEl.textContent = text; setTimeout(function () { if (statusEl.textContent === text) statusEl.textContent = ""; }, 4000); } };

    var applyHash = function () {                     /* a share link carries the amount after the #, where no server sees it */
      var h = new URLSearchParams(location.hash.replace(/^#/, ""));
      if (h.get("amount")) input.value = h.get("amount");
      var r = form.querySelector('input[name="view"][value="' + (h.get("view") === "agency" ? "agency" : "purpose") + '"]');
      if (r && (h.get("view") || h.get("amount"))) r.checked = true;
    };
    applyHash();
    window.addEventListener("hashchange", function () { applyHash(); render(); });
    input.addEventListener("input", render);
    input.addEventListener("blur", function () {
      var c = toCents(input.value);
      input.value = (c / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (c % 100n ? "." + ("0" + (c % 100n).toString()).slice(-2) : "");
    });
    Array.prototype.forEach.call(form.querySelectorAll('input[name="view"]'), function (el) { el.addEventListener("change", render); });
    Array.prototype.forEach.call(form.querySelectorAll("[data-amount]"), function (b) {
      b.addEventListener("click", function () { input.value = Number(b.dataset.amount).toLocaleString("en-US"); render(); });
    });
    if ($("copy-link")) $("copy-link").addEventListener("click", function () {
      var link = shareLink();
      copy(link, function () { say("Link copied. It carries only the amount, after the #."); }, function () { say("Copy this link: " + link); });
    });
    if ($("download")) $("download").addEventListener("click", function () {
      var s = current(), lines = ["THE PEOPLE'S RECEIPT", "Federal fiscal year " + data.fy + " · " + s.v.label.toLowerCase(), "", "Amount: " + usd(s.amount), ""];
      s.v.lines.forEach(function (l, i) { lines.push(l[0] + ": " + usd(s.parts[i]) + " (" + share(s.lines[i], s.total) + ")"); });
      lines.push("", "Total: " + usd(s.parts.reduce(function (x, c) { return x + c; }, 0n)), "",
        "Illustrative allocation. Federal receipts are not earmarked taxpayer by taxpayer; each line's share of total net outlays is applied to the amount entered.",
        "Source: Monthly Treasury Statement, U.S. Treasury, final statement for fiscal year " + data.fy + " (dated " + data.record_date + "), read " + data.read + ".",
        "https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/", shareLink());
      download("federal-taxpayer-receipt-fy" + data.fy + ".txt", lines.join("\n") + "\n");
    });
    if ($("print")) $("print").addEventListener("click", function () { window.print(); });
    render();
  }

  /* ------------------------------------------------------------------ comment deadlines */
  var today = easternToday();
  var stale = $("stale");
  if (stale && stale.dataset.built) {
    var age = dayNumber(today) - dayNumber(stale.dataset.built);
    if (age > 2) {
      stale.hidden = false;
      stale.textContent = "This list was built " + age + " days ago (" + shortDate(stale.dataset.built) + "). Documents that have closed since then are hidden, " +
        "but new ones are missing. Check FederalRegister.gov for the current list.";
    }
  }
  var refreshStatic = function () {
    Array.prototype.forEach.call(document.querySelectorAll("li.doc[data-closes]"), function (li) {
      var closes = li.dataset.closes, left = li.querySelector(".left");
      if (closes < today) li.hidden = true;
      else if (left) left.textContent = leftLabel(closes, today);
    });
  };
  refreshStatic();

  var finder = $("finder");
  if (finder) {
    var els = { q: finder.querySelector("[name=q]"), t: finder.querySelector("[name=t]"), a: finder.querySelector("[name=a]"), w: finder.querySelector("[name=w]") };
    var out = $("docs"), count = $("count"), more = $("more"), PAGE = 60, shown = PAGE, idx = null;
    var row = function (d) {
      /* d = [number, title, type index, [agency indexes], closes, published, url, comment url, abstract, dockets] */
      var bits = [idx.types[d[2]], d[3].map(function (i) { return idx.agencies[i]; }).join("; ")];
      if (d[9]) bits.push(d[9].split("; ")[0]);
      bits.push("published " + shortDate(d[5]));
      var comment = d[7] ? '<a class="btn sm" href="' + esc(d[7]) + '" rel="noopener">Comment</a>' : '<span class="how">See the document for how to comment</span>';
      return '<li class="doc" data-closes="' + esc(d[4]) + '"><div><a href="' + esc(d[6]) + '" rel="noopener">' + esc(d[1]) + "</a><small>" + esc(bits.filter(Boolean).join(" · ")) +
        "</small>" + (d[8] && els.q.value.trim() ? "<p>" + esc(d[8]) + "</p>" : "") + '</div><div class="due"><b>' + shortDate(d[4]) + '</b><span class="left">' + leftLabel(d[4], today) + "</span>" + comment + "</div></li>";
    };
    var render2 = function () {
      var words = els.q.value.trim().toLowerCase().split(/\s+/).filter(Boolean), t = els.t.value, a = els.a.value, w = +els.w.value || 0;
      var open = idx.docs.filter(function (d) { return d[4] >= today; });
      var list = open.filter(function (d) {
        if (t !== "" && String(d[2]) !== t) return false;
        if (a !== "" && d[3].indexOf(+a) < 0) return false;
        if (w && dayNumber(d[4]) - dayNumber(today) > w) return false;
        if (!words.length) return true;
        var hay = (d[1] + " " + d[8] + " " + d[9] + " " + d[0] + " " + d[3].map(function (i) { return idx.agencies[i]; }).join(" ")).toLowerCase();
        return words.every(function (x) { return hay.indexOf(x) >= 0; });
      });
      count.textContent = list.length.toLocaleString("en-US") + (list.length === 1 ? " document" : " documents") + " open for comment" +
        (list.length === open.length ? "" : " of " + open.length.toLocaleString("en-US")) + ", soonest deadline first.";
      out.innerHTML = list.slice(0, shown).map(row).join("") || '<li class="doc"><div>Nothing open matches. Try fewer words.</div></li>';
      more.hidden = list.length <= shown;
      var q = new URLSearchParams();
      Object.keys(els).forEach(function (k) { if (els[k].value) q.set(k, els[k].value); });
      var qs = q.toString();
      history.replaceState(null, "", location.pathname + (qs ? "?" + qs : ""));
    };
    fetch(base + "/assets/comments.json").then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }).then(function (d) {
      idx = d;
      d.types.forEach(function (n, i) { els.t.appendChild(new Option(n, String(i))); });
      d.agencies.forEach(function (n, i) { els.a.appendChild(new Option(n, String(i))); });
      var params = new URLSearchParams(location.search);
      Object.keys(els).forEach(function (k) { if (params.get(k)) els[k].value = params.get(k); });
      var timer;
      Object.keys(els).forEach(function (k) {
        els[k].addEventListener("input", function () { shown = PAGE; clearTimeout(timer); timer = setTimeout(render2, 100); });
      });
      more.addEventListener("click", function () { shown += PAGE * 2; render2(); });
      finder.hidden = false;
      render2();
    }).catch(function () { /* the static list stays as it is */ });
  }

  /* ------------------------------------------------------------------ FOIA request builder */
  var foia = $("foia-form");
  if (foia) {
    var val = function (id) { return ($(id).value || "").trim(); };
    var longDate = function (iso) {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return "";
      var p = iso.split("-");
      return ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"][+p[1] - 1] + " " + (+p[2]) + ", " + p[0];
    };
    var CATEGORY = {
      news: "For fee purposes, I am a representative of the news media, and this request is made for news gathering and not for commercial use.",
      edu: "For fee purposes, this request is made for an educational or noncommercial scientific institution, for scholarly or scientific research and not for commercial use.",
      personal: "For fee purposes, this request is for personal, non-commercial use.",
      commercial: "For fee purposes, this request is for commercial use."
    };
    var buildLetter = function () {
      var agency = val("foia-agency") || "[AGENCY OR OFFICE]", records = val("foia-records") || "[DESCRIBE THE RECORDS]";
      var start = longDate(val("foia-start")), end = longDate(val("foia-end")), cap = val("foia-cap").replace(/[^0-9]/g, "") || "25";
      var cat = $("foia-category").value, waiver = $("foia-waiver"), expedite = $("foia-expedite").checked;
      waiver.disabled = cat === "commercial";
      if (waiver.disabled) waiver.checked = false;
      $("waiver-box").hidden = !waiver.checked;
      $("expedite-box").hidden = !expedite;
      var now = new Date(), todayLong = longDate(now.getFullYear() + "-" + ("0" + (now.getMonth() + 1)).slice(-2) + "-" + ("0" + now.getDate()).slice(-2));
      var out = ["Freedom of Information Act Request", "", todayLong, "", "To: FOIA Officer, " + agency, "",
        "Under the Freedom of Information Act, 5 U.S.C. § 552, I request copies of the following records:", "", records, ""];
      if (start && end) out.push("Please search for records dated from " + start + " through " + end + ".", "");
      else if (start) out.push("Please search for records dated from " + start + " to the date of your search.", "");
      else if (end) out.push("Please search for records dated up to " + end + ".", "");
      out.push("Please provide " + $("foia-format").value + ". If any part of a record is withheld, please release every reasonably segregable portion and cite the exemption that applies to each withholding.", "");
      if (CATEGORY[cat]) out.push(CATEGORY[cat], "");
      out.push("I agree to pay fees up to $" + Number(cap).toLocaleString("en-US") + ". Please tell me before the cost goes above that amount.");
      if (waiver.checked) {
        out.push("", "I also request a waiver of fees. Disclosure of these records is in the public interest because it is likely to contribute significantly to public " +
          "understanding of the operations or activities of the government, and it is not primarily in my commercial interest." + (val("foia-waiver-why") ? " " + val("foia-waiver-why") : ""));
      }
      if (expedite) {
        out.push("", "I request expedited processing. " + (val("foia-expedite-why") || "[EXPLAIN THE COMPELLING NEED]") +
          " I certify that this statement is true and correct to the best of my knowledge and belief.");
      }
      out.push("", "I look forward to your determination within 20 working days, as the statute provides. Please send me a tracking number, and contact me if any part of this request is unclear.",
        "", "Sincerely,", val("foia-name") || "[YOUR NAME]\n[HOW TO REACH YOU]");
      var text = out.join("\n");
      $("letter").textContent = text;
      return text;
    };
    var tell = function (text) { $("foia-status").textContent = text; };
    foia.addEventListener("input", buildLetter);
    foia.addEventListener("change", buildLetter);
    $("foia-copy").addEventListener("click", function () {
      copy(buildLetter(), function () { tell("Request copied. Check the agency's own submission rules before you send it."); },
        function () { tell("Copying is not available here. Select the text of the request and copy it."); });
    });
    $("foia-download").addEventListener("click", function () { download("foia-request.txt", buildLetter() + "\n"); tell("Saved as foia-request.txt."); });
    $("foia-print").addEventListener("click", function () { buildLetter(); window.print(); });
    buildLetter();
  }
})();
