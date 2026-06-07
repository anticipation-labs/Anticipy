export const metadata = {
  title: "Anticipy for Mac",
  description: "Download the local Anticipy Mac app.",
  icons: {
    icon: "/favicon.svg",
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
