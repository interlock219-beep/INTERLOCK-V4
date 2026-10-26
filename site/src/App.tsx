import { lazy, Suspense, useEffect } from 'react';
import { Route, Routes, useLocation } from 'react-router-dom';
import { Header } from './components/Header';
import { Footer } from './components/Footer';
import { HomePage } from './pages/Home';

// Route-level code splitting keeps the initial bundle small; the home page
// stays eager because it is the entry point for most visits.
const FeaturesPage = lazy(() => import('./pages/Features').then((m) => ({ default: m.FeaturesPage })));
const DemoPage = lazy(() => import('./pages/Demo').then((m) => ({ default: m.DemoPage })));
const DownloadPage = lazy(() => import('./pages/Download').then((m) => ({ default: m.DownloadPage })));
const DocsPage = lazy(() => import('./pages/Docs').then((m) => ({ default: m.DocsPage })));
const SafetyPage = lazy(() => import('./pages/Safety').then((m) => ({ default: m.SafetyPage })));
const PricingPage = lazy(() => import('./pages/Pricing').then((m) => ({ default: m.PricingPage })));
const UsagePage = lazy(() => import('./pages/Usage').then((m) => ({ default: m.UsagePage })));
const BlogPage = lazy(() => import('./pages/Blog').then((m) => ({ default: m.BlogPage })));
const ArticlePage = lazy(() => import('./pages/Article').then((m) => ({ default: m.ArticlePage })));
const BetaPage = lazy(() => import('./pages/Beta').then((m) => ({ default: m.BetaPage })));
const AboutPage = lazy(() => import('./pages/About').then((m) => ({ default: m.AboutPage })));
const NotFoundPage = lazy(() => import('./pages/NotFound').then((m) => ({ default: m.NotFoundPage })));

function RouteFallback() {
  return (
    <div className="container route-loading" role="status" aria-live="polite">
      Loading…
    </div>
  );
}

function ScrollToTop() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash) {
      const id = decodeURIComponent(hash.slice(1));
      // The target may render a tick after route change; retry once.
      const scrollToId = () => {
        const el = document.getElementById(id);
        if (el) {
          el.scrollIntoView({ block: 'start' });
          return true;
        }
        return false;
      };
      if (!scrollToId()) {
        const raf = requestAnimationFrame(scrollToId);
        return () => cancelAnimationFrame(raf);
      }
      return;
    }
    window.scrollTo({ top: 0, behavior: 'auto' });
  }, [pathname, hash]);
  return null;
}

export function App() {
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <Header />
      <ScrollToTop />
      <main id="main-content" tabIndex={-1}>
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/features" element={<FeaturesPage />} />
            <Route path="/demo" element={<DemoPage />} />
            <Route path="/download" element={<DownloadPage />} />
            <Route path="/docs" element={<DocsPage />} />
            <Route path="/docs/:slug" element={<DocsPage />} />
            <Route path="/safety" element={<SafetyPage />} />
            <Route path="/pricing" element={<PricingPage />} />
            <Route path="/usage" element={<UsagePage />} />
            <Route path="/blog" element={<BlogPage />} />
            <Route path="/blog/:slug" element={<ArticlePage />} />
            <Route path="/beta" element={<BetaPage />} />
            <Route path="/about" element={<AboutPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Suspense>
      </main>
      <Footer />
    </>
  );
}

export default App;
