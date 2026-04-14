import PlayersClient from "./PlayersClient";

export default function PlayersPage() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-xl font-bold text-white">Players</h1>
        <p className="text-sm text-gray-500 mt-1">
          All scored players ordered by expected LTV (90d)
        </p>
      </div>
      <PlayersClient />
    </div>
  );
}
