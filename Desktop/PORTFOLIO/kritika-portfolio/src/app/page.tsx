import Navbar from '@/components/navigation/Navbar';
import ScrollProgress from '@/components/navigation/ScrollProgress';
import Hero from '@/components/hero/Hero';
import About from '@/components/about/About';
import Experience from '@/components/experience/Experience';
import Education from '@/components/education/Education';
import Projects from '@/components/projects/Projects';
import Skills from '@/components/skills/Skills';
import Achievements from '@/components/achievements/Achievements';
import Blog from '@/components/blog/Blog';
import Contact from '@/components/contact/Contact';
import Footer from '@/components/footer/Footer';

export default function Home() {
  return (
    <>
      <ScrollProgress />
      <Navbar />
      <main className="min-h-screen">
        <Hero />
        <About />
        <Experience />
        <Education />
        <Projects />
        <Skills />
        <Achievements />
        <Blog />
        <Contact />
      </main>
      <Footer />
    </>
  );
}
