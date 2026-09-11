(function () {
  "use strict";

  var navbar = document.querySelector("[data-ge-navbar]");
  if (!navbar) return;

  var isLanding = window.location.pathname === "/";
  var sections = ["inicio", "cotizaciones", "conversor", "seguridad"];

  var mobileTrigger = navbar.querySelector("[data-mobile-trigger]");
  var mobileMenu = document.getElementById("ge-mobile-menu");
  var profileTrigger = navbar.querySelector("[data-profile-trigger]");
  var profileMenu = document.getElementById("ge-profile-menu");
  var iconMenu = navbar.querySelector("[data-icon-menu]");
  var iconClose = navbar.querySelector("[data-icon-close]");
  var sectionLinks = navbar.querySelectorAll("[data-nav-section]");

  function setMobileOpen(open) {
    if (!mobileMenu || !mobileTrigger) return;
    mobileMenu.hidden = !open;
    mobileTrigger.setAttribute("aria-expanded", String(open));
    mobileTrigger.setAttribute(
      "aria-label",
      open ? "Cerrar navegación" : "Abrir navegación",
    );
    if (iconMenu) iconMenu.hidden = open;
    if (iconClose) iconClose.hidden = !open;
  }

  function setProfileOpen(open) {
    if (!profileMenu || !profileTrigger) return;
    profileMenu.hidden = !open;
    profileTrigger.setAttribute("aria-expanded", String(open));
  }

  function anyOpen() {
    return (
      (mobileMenu && !mobileMenu.hidden) ||
      (profileMenu && !profileMenu.hidden)
    );
  }

  function closeAll() {
    setMobileOpen(false);
    setProfileOpen(false);
  }

  function sectionFromHash() {
    var section = window.location.hash.replace("#", "");
    return sections.indexOf(section) !== -1 ? section : "inicio";
  }

  function setActiveFromSection(section) {
    if (!isLanding) return;
    sectionLinks.forEach(function (link) {
      var linkSection = link.getAttribute("data-nav-section");
      var isActive = linkSection === section;
      if (isActive) {
        link.classList.add("is-active");
        link.setAttribute("aria-current", "location");
      } else {
        link.classList.remove("is-active");
        link.removeAttribute("aria-current");
      }
    });
  }

  var frame = 0;
  function syncActiveSection() {
    if (!isLanding) return;
    window.cancelAnimationFrame(frame);
    frame = window.requestAnimationFrame(function () {
      if (!isLanding) return;
      var marker = window.scrollY + 96;
      var current = "inicio";
      sections.forEach(function (section) {
        var element = document.getElementById(section);
        if (element && element.offsetTop <= marker) current = section;
      });
      setActiveFromSection(current);
    });
  }

  function onScroll() {
    var scrolled = window.scrollY > 16;
    navbar.classList.toggle("ge-navbar--scrolled", scrolled);
    navbar.classList.toggle("ge-navbar--landing", isLanding && !scrolled);
    syncActiveSection();
  }

  setMobileOpen(false);
  setProfileOpen(false);
  onScroll();
  setActiveFromSection(sectionFromHash());

  if (isLanding) {
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("hashchange", function () {
      setActiveFromSection(sectionFromHash());
    });
  } else {
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  if (mobileTrigger) {
    mobileTrigger.addEventListener("click", function () {
      var wasOpen =
        mobileMenu && mobileTrigger.getAttribute("aria-expanded") === "true";
      setMobileOpen(!wasOpen);
      setProfileOpen(false);
    });
  }

  if (profileTrigger) {
    profileTrigger.addEventListener("click", function () {
      var wasOpen =
        profileMenu &&
        profileTrigger.getAttribute("aria-expanded") === "true";
      setProfileOpen(!wasOpen);
    });
  }

  document.addEventListener("pointerdown", function (event) {
    if (navbar.contains(event.target)) return;
    if (anyOpen()) closeAll();
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && anyOpen()) closeAll();
  });

  navbar.querySelectorAll("[data-close-menus]").forEach(function (control) {
    control.addEventListener("click", closeAll);
  });

  sectionLinks.forEach(function (link) {
    link.addEventListener("click", function () {
      setActiveFromSection(link.getAttribute("data-nav-section"));
      closeAll();
    });
  });
})();