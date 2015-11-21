class CreateTiers < ActiveRecord::Migration
  def change
    create_table :tiers do |t|
      t.string :cart
      t.integer :number
      t.string :name
      t.text :notes

      t.timestamps null: false
    end
    add_index :tiers, :number, unique: true
  end
end
