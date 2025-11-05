"use client";

import Header from "@/components/header";
import InfoCard from "@/components/infoCards";
import StatsSkeleton from "@/components/StatsSkeleton";
import CardSkeleton from "@/components/CardSkeleton";

export default function Loading() {
  return (
    <div className="min-h-screen container mx-auto px-4 py-8 md:py-16">
      <Header />
      <main className="space-y-12 md:space-y-16">
        <InfoCard />
        <div className="mb-8">
          <StatsSkeleton />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[...Array(3)].map((_, idx) => (
            <CardSkeleton key={idx} />
          ))}
        </div>
      </main>
    </div>
  );
}
