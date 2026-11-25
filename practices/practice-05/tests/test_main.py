import pytest


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello, QA!"}


@pytest.mark.parametrize(
    "name,price",
    [("Laptop", 999.99), ("Phone", 499.99), ("Keyboard", 49.99)],
    ids=["laptop", "phone", "keyboard"],
)
def test_create_item(client, name, price):
    data = {"name": name, "price": price}
    response = client.post("/items/", json=data)
    assert response.status_code == 201
    assert response.json()["message"] == f"Item {name} created"
    assert client.get(f"/items/{name}").json() == data


def test_create_duplicate_item(client):
    data = {"name": "Laptop", "price": 999.99}
    assert client.post("/items/", json=data).status_code == 201
    response = client.post("/items/", json=data)
    assert response.status_code == 400
    assert response.json()["detail"] == "Item already exists"


def test_get_item(client):
    data = {"name": "Laptop", "price": 999.99}
    assert client.post("/items/", json=data).status_code == 201
    response = client.get("/items/Laptop")
    assert response.status_code == 200
    assert response.json() == data


def test_get_non_existent_item(client):
    response = client.get("/items/Nonexistent")
    assert response.status_code == 404
    assert response.json()["detail"] == "Item not found"


def test_get_all_items(client):
    assert client.get("/items/").json() == []
    data = {"name": "Laptop", "price": 999.99}
    assert client.post("/items/", json=data).status_code == 201
    response = client.get("/items/")
    assert response.status_code == 200
    assert response.json() == [data]


def test_delete_item(client):
    data = {"name": "Laptop", "price": 999.99}
    assert client.post("/items/", json=data).status_code == 201
    response = client.delete("/items/Laptop")
    assert response.status_code == 200
    assert response.json() == {"message": "Item Laptop deleted"}
    assert client.get("/items/Laptop").status_code == 404
    assert client.get("/items/").json() == []


def test_delete_non_existent_item(client):
    response = client.delete("/items/Nonexistent")
    assert response.status_code == 404
    assert response.json()["detail"] == "Item not found"


@pytest.mark.parametrize(
    "data",
    [
        {"name": "Laptop", "price": -1},
        {"name": "Laptop"},
        {"name": "Laptop", "price": "invalid"},
        {"name": "", "price": 10},
    ],
    ids=["negative-price", "missing-price", "wrong-type", "empty-name"],
)
def test_invalid_item(client, data):
    assert client.post("/items/", json=data).status_code == 422
    assert client.get("/items/").json() == []
