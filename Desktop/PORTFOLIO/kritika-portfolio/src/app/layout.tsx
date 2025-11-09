import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Kritika Singh | Full-Stack Developer & ML Engineer",
  description: "Portfolio of Kritika Singh - Full-Stack Developer, Shopify Specialist, and ML Engineer. Building scalable e-commerce solutions and data-driven applications.",
  keywords: ["Full-Stack Developer", "Shopify Developer", "ML Engineer", "React", "Next.js", "Python", "TensorFlow"],
  authors: [{ name: "Kritika Singh" }],
  openGraph: {
    title: "Kritika Singh | Full-Stack Developer & ML Engineer",
    description: "Portfolio of Kritika Singh - Full-Stack Developer, Shopify Specialist, and ML Engineer",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="scroll-smooth">
      <body className={`${inter.variable} font-sans antialiased`}>
        {children}
      </body>
    </html>
  );
}
