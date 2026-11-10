PRODUCT = {"name": "Mouse", "price_cents": 1999, "stock": 5}


def test_product_crud(client):
    created = client.post("/products", json=PRODUCT)
    assert created.status_code == 201
    pid = created.json()["id"]

    assert client.get(f"/products/{pid}").json()["name"] == "Mouse"
    assert len(client.get("/products").json()) == 1

    updated = client.put(f"/products/{pid}", json={**PRODUCT, "stock": 9})
    assert updated.json()["stock"] == 9

    assert client.delete(f"/products/{pid}").status_code == 204
    assert client.get(f"/products/{pid}").status_code == 404


def test_product_validation(client):
    res = client.post("/products", json={"name": "", "price_cents": -1})
    assert res.status_code == 422
