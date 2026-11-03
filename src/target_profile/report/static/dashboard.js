(function () {
  "use strict";

  var dataEl = document.getElementById("chart-data");
  var payload = {};
  if (dataEl) {
    try {
      payload = JSON.parse(dataEl.textContent);
    } catch (error) {
      payload = {};
    }
  }
  var palette = ["#55d6be", "#6ea8fe", "#f0b053", "#f27d9a", "#75d88a", "#a78bfa"];

  if (window.echarts) {
    echarts.registerTheme("target", {
      color: palette,
      backgroundColor: "transparent",
      animation: false,
      textStyle: {
        color: "#c9d6e5",
        fontFamily: '"Space Grotesk", system-ui, "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif'
      },
      title: { textStyle: { color: "#e7eef7" } },
      tooltip: {
        backgroundColor: "#0f1620",
        borderColor: "rgba(120,160,200,.3)",
        textStyle: { color: "#e7eef7", fontSize: 12 }
      },
      categoryAxis: {
        axisLine: { lineStyle: { color: "rgba(120,160,200,.25)" } },
        axisLabel: { color: "#8b9bb0" },
        splitLine: { show: false }
      },
      valueAxis: {
        axisLine: { show: false },
        axisLabel: { color: "#8b9bb0" },
        splitLine: { lineStyle: { color: "rgba(120,160,200,.12)" } }
      },
      legend: { textStyle: { color: "#8b9bb0" } }
    });

    echarts.registerTheme("target-print", {
      color: ["#0f6b5c", "#1f4f8f", "#9a5b1e", "#a8435f", "#3d7a4a", "#6b5bab"],
      backgroundColor: "transparent",
      animation: false,
      textStyle: {
        color: "#39414d",
        fontFamily: '"Space Grotesk", system-ui, "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif'
      },
      title: { textStyle: { color: "#20242c" } },
      tooltip: {
        backgroundColor: "#ffffff",
        borderColor: "rgba(15,107,92,.25)",
        textStyle: { color: "#20242c", fontSize: 12 }
      },
      categoryAxis: {
        axisLine: { lineStyle: { color: "rgba(57,65,77,.25)" } },
        axisLabel: { color: "#7b7365" },
        splitLine: { show: false }
      },
      valueAxis: {
        axisLine: { show: false },
        axisLabel: { color: "#7b7365" },
        splitLine: { lineStyle: { color: "rgba(57,65,77,.12)" } }
      },
      legend: { textStyle: { color: "#7b7365" } }
    });
  }

  var isPrint = document.body && document.body.getAttribute("data-theme") === "print";
  var themeName = isPrint ? "target-print" : "target";

  var charts = [];
  Array.prototype.forEach.call(
    document.querySelectorAll(".chart[data-chart-id]"),
    function (el) {
      var id = el.getAttribute("data-chart-id");
      var entry = payload[id];
      if (!window.echarts || !entry) {
        el.innerHTML = '<div class="empty"><div class="empty-icon">×</div><p>Chart unavailable</p></div>';
        return;
      }
      var chart = echarts.init(el, themeName, { renderer: "canvas" });
      var option = entry.option || {};
      option.animation = false;
      chart.setOption(option);
      charts.push(chart);
    }
  );

  var resizeTimer = null;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      charts.forEach(function (chart) { chart.resize(); });
    }, 120);
  });

  window.__chartsReady = true;

  var progressBar = document.querySelector(".reading-progress span");
  function updateProgress() {
    if (!progressBar) return;
    var doc = document.documentElement;
    var max = doc.scrollHeight - window.innerHeight;
    var ratio = max > 0 ? doc.scrollTop / max : 0;
    ratio = Math.max(0, Math.min(1, ratio));
    progressBar.style.width = (ratio * 100).toFixed(2) + "%";
  }
  window.addEventListener("scroll", updateProgress, { passive: true });
  window.addEventListener("resize", updateProgress);
  updateProgress();

  window.__snapshotCharts = function () {
    charts.forEach(function (chart) {
      var url = chart.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: isPrint ? "#fffdf8" : "#0b1118" });
      var img = document.createElement("img");
      img.src = url;
      img.className = "chart-snapshot";
      img.alt = "chart";
      chart.getDom().replaceWith(img);
    });
    charts = [];
  };

  var links = Array.prototype.slice.call(document.querySelectorAll(".toc a[href^='#']"));
  var byId = {};
  links.forEach(function (link) {
    byId[link.getAttribute("href").slice(1)] = link;
  });
  var sections = Array.prototype.slice.call(document.querySelectorAll("section[id]"));

  if ("IntersectionObserver" in window && sections.length) {
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          links.forEach(function (link) { link.classList.remove("active"); });
          var link = byId[entry.target.id];
          if (link) link.classList.add("active");
        });
      },
      { rootMargin: "-18% 0px -72% 0px", threshold: 0 }
    );
    sections.forEach(function (section) { observer.observe(section); });
  }

  var reduceMotion =
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var revealTargets = document.querySelectorAll(".reveal");
  if (!reduceMotion && "IntersectionObserver" in window) {
    var revealObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("in");
            revealObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.08 }
    );
    Array.prototype.forEach.call(revealTargets, function (el) { revealObserver.observe(el); });
  } else {
    Array.prototype.forEach.call(revealTargets, function (el) { el.classList.add("in"); });
  }
})();
