json.array!(@tiers) do |tier|
  json.extract! tier, :id, :cart, :number, :name, :notes
  json.url tier_url(tier, format: :json)
end
