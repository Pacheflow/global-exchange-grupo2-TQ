import { useEffect, useRef, useState } from "react";

import { AppIcon } from "./icons/AppIcon";
import "./navbar.css";

export interface NavbarProps {
  authenticated?: string;
  adminUrl?: string;
  converterUrl?: string;
  currentClient?: string;
  dashboardUrl?: string;
  homeUrl?: string;
  loginUrl?: string;
  logoutUrl?: string;
  ratesUrl?: string;
  registerUrl?: string;
  roleLabel?: string;
  securityUrl?: string;
  userEmail?: string;
  userName?: string;
}

interface NavLink {
  href: string;
  label: string;
  section: "inicio" | "cotizaciones" | "conversor" | "seguridad";
}

export function Navbar({
  authenticated = "false",
  adminUrl,
  converterUrl = "/#conversor",
  currentClient,
  dashboardUrl = "/panel/",
  homeUrl = "/",
  loginUrl = "/login/",
  logoutUrl = "/logout/",
  ratesUrl = "/#cotizaciones",
  registerUrl = "/registro/",
  roleLabel,
  securityUrl = "/#seguridad",
  userEmail,
  userName,
}: NavbarProps) {
  const isAuthenticated = authenticated === "true";
  const isLandingPage =
    typeof window !== "undefined" && window.location.pathname === "/";
  const sectionFromHash = () => {
    if (typeof window === "undefined") return "inicio";
    const section = window.location.hash.replace("#", "");
    return ["cotizaciones", "conversor", "seguridad"].includes(section)
      ? section
      : "inicio";
  };
  const [activeSection, setActiveSection] = useState(sectionFromHash);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const navbarRef = useRef<HTMLElement>(null);

  const mainLinks: NavLink[] = [
    { href: homeUrl, label: "Inicio", section: "inicio" },
    { href: ratesUrl, label: "Cotizaciones", section: "cotizaciones" },
    { href: converterUrl, label: "Conversor", section: "conversor" },
    { href: securityUrl, label: "Seguridad", section: "seguridad" },
  ];

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 16);
    handleScroll();
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    if (!isLandingPage) return;

    let frame = 0;
    const sections = ["inicio", "cotizaciones", "conversor", "seguridad"] as const;
    const syncActiveSection = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        const marker = window.scrollY + 96;
        let current: typeof sections[number] = "inicio";
        sections.forEach((section) => {
          const element = document.getElementById(section);
          if (element && element.offsetTop <= marker) current = section;
        });
        setActiveSection(current);
      });
    };

    const handleHashChange = () => setActiveSection(sectionFromHash());
    syncActiveSection();
    window.addEventListener("scroll", syncActiveSection, { passive: true });
    window.addEventListener("hashchange", handleHashChange);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("scroll", syncActiveSection);
      window.removeEventListener("hashchange", handleHashChange);
    };
  }, [isLandingPage]);

  useEffect(() => {
    if (!mobileOpen && !profileOpen) {
      return;
    }

    const handlePointerDown = (event: PointerEvent) => {
      if (!navbarRef.current?.contains(event.target as Node)) {
        setMobileOpen(false);
        setProfileOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileOpen(false);
        setProfileOpen(false);
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [mobileOpen, profileOpen]);

  const displayName = userName?.trim() || "Usuario";
  const initial = Array.from(displayName)[0]?.toLocaleUpperCase("es-PY") ?? "U";

  const closeMenus = () => {
    setMobileOpen(false);
    setProfileOpen(false);
  };

  const renderMainLinks = (className: string) => (
    <div className={className}>
      {mainLinks.map((link) => (
        <a
          key={link.label}
          href={link.href}
          className={isLandingPage && activeSection === link.section ? "is-active" : undefined}
          aria-current={isLandingPage && activeSection === link.section ? "location" : undefined}
          onClick={() => {
            if (isLandingPage) setActiveSection(link.section);
            closeMenus();
          }}
        >
          {link.label}
        </a>
      ))}
    </div>
  );

  return (
    <nav
      ref={navbarRef}
      {...{ "up-nav": "false" }}
      className={`ge-navbar${scrolled ? " ge-navbar--scrolled" : ""}${
        isLandingPage && !scrolled ? " ge-navbar--landing" : ""
      }`}
      aria-label="Navegación principal"
    >
      <div className="ge-navbar__inner">
        <a
          className="ge-navbar__brand"
          href={homeUrl}
          aria-label="Global Exchange, inicio"
          onClick={closeMenus}
        >
          <span className="ge-navbar__brand-icon">
            <AppIcon name="globe" size={27} />
          </span>
          <span className="ge-navbar__wordmark">
            <strong>GLOBAL</strong>
            <small>EXCHANGE</small>
          </span>
        </a>

        {renderMainLinks("ge-navbar__links")}

        <div className="ge-navbar__actions">
          {isAuthenticated ? (
            <>
              <a className="ge-navbar__dashboard-link" href={dashboardUrl}>
                <AppIcon name="dashboard" size={17} />
                Dashboard
              </a>
              {adminUrl ? (
                <a className="ge-navbar__admin-link" href={adminUrl}>
                  <AppIcon name="roles" size={17} />
                  Administración
                </a>
              ) : null}
              <div className="ge-navbar__profile">
                <button
                  className="ge-navbar__profile-trigger"
                  type="button"
                  aria-expanded={profileOpen}
                  aria-controls="ge-profile-menu"
                  onClick={() => setProfileOpen((open) => !open)}
                >
                  <span className="ge-navbar__avatar" aria-hidden="true">
                    {initial}
                  </span>
                  <span className="ge-navbar__profile-copy">
                    <strong>{displayName}</strong>
                    {roleLabel ? <small>{roleLabel}</small> : null}
                  </span>
                  <AppIcon name="chevron-down" size={14} />
                </button>

                {profileOpen ? (
                  <div
                    className="ge-navbar__profile-menu"
                    id="ge-profile-menu"
                  >
                    <div className="ge-navbar__profile-summary">
                      <span className="ge-navbar__profile-title">
                        <AppIcon name="user" size={16} />
                        Perfil
                      </span>
                      <strong>{displayName}</strong>
                      {userEmail ? <span>{userEmail}</span> : null}
                      {roleLabel ? <small>{roleLabel}</small> : null}
                      {currentClient ? (
                        <span className="ge-navbar__client">
                          Cliente: {currentClient}
                        </span>
                      ) : null}
                    </div>
                    <a href={dashboardUrl} onClick={closeMenus}>
                      <AppIcon name="dashboard" size={17} />
                      Ir al dashboard
                    </a>
                    {adminUrl ? (
                      <a href={adminUrl} onClick={closeMenus}>
                        <AppIcon name="roles" size={17} />
                        Administración
                      </a>
                    ) : null}
                    <a
                      className="ge-navbar__logout"
                      href={logoutUrl}
                      onClick={closeMenus}
                    >
                      <AppIcon name="logout" size={17} />
                      Cerrar sesión
                    </a>
                  </div>
                ) : null}
              </div>
            </>
          ) : (
            <>
              <a className="ge-navbar__login" href={loginUrl}>
                <AppIcon name="login" size={17} />
                Iniciar sesión
              </a>
              <a className="ge-navbar__register" href={registerUrl}>
                <AppIcon name="user-plus" size={17} />
                Registrarse
              </a>
            </>
          )}
        </div>

        <button
          className="ge-navbar__mobile-trigger"
          type="button"
          aria-expanded={mobileOpen}
          aria-controls="ge-mobile-menu"
          aria-label={mobileOpen ? "Cerrar navegación" : "Abrir navegación"}
          onClick={() => {
            setMobileOpen((open) => !open);
            setProfileOpen(false);
          }}
        >
          <AppIcon name={mobileOpen ? "close" : "menu"} size={23} />
        </button>
      </div>

      {mobileOpen ? (
        <div className="ge-navbar__mobile-menu" id="ge-mobile-menu">
          {renderMainLinks("ge-navbar__mobile-links")}
          {isAuthenticated ? (
            <div className="ge-navbar__mobile-account">
              <div>
                <span className="ge-navbar__avatar" aria-hidden="true">
                  {initial}
                </span>
                <span>
                  <strong>{displayName}</strong>
                  {roleLabel ? <small>{roleLabel}</small> : null}
                </span>
              </div>
              {currentClient ? <p>Cliente: {currentClient}</p> : null}
              <a href={dashboardUrl} onClick={closeMenus}>
                <AppIcon name="dashboard" size={17} />
                Dashboard
              </a>
              {adminUrl ? (
                <a href={adminUrl} onClick={closeMenus}>
                  <AppIcon name="roles" size={17} />
                  Administración
                </a>
              ) : null}
              <a
                className="ge-navbar__logout"
                href={logoutUrl}
                onClick={closeMenus}
              >
                <AppIcon name="logout" size={17} />
                Cerrar sesión
              </a>
            </div>
          ) : (
            <div className="ge-navbar__mobile-auth">
              <a className="ge-navbar__login" href={loginUrl}>
                <AppIcon name="login" size={17} />
                Iniciar sesión
              </a>
              <a className="ge-navbar__register" href={registerUrl}>
                <AppIcon name="user-plus" size={17} />
                Registrarse
              </a>
            </div>
          )}
        </div>
      ) : null}
    </nav>
  );
}
