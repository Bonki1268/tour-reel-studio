import { redirect } from "next/navigation";

export default function Home() {
  redirect(`/projects/${process.env.NEXT_PUBLIC_DEMO_PROJECT_ID ?? "demo"}`);
}
