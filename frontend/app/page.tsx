import type { Metadata } from "next";
import HomeContent from "./HomeContent";
import "./landing.css";
export const metadata: Metadata = { title: "VIN-Twin — цифровой двойник завода", description: "Качество, оборудование и план в одной панели. Сравнение производственных сценариев." };
export default function Home() { return <HomeContent />; }
